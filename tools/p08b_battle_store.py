"""Opt-in profile13 battle reservations/results on the existing SQLite writer.

Only a trusted, fenced gateway calls this boundary. Clients never supply a
loadout, inventory state, prices, source paths or an account authentication claim.
Whole-process crashes abort/refund unfinished reservations; this is deliberately
not durable per-shot simulation. Normal returns persist actual AP expenditure.
"""
from __future__ import annotations

from copy import deepcopy
import json
import re
import uuid

from game_profile_tx import TransactionError, _bounded_id, _revision
from p09e_research_store import ResearchStore, MAX_OWNED
from p09d_ammo_store import require, sha
from p09d_ammo_projection import canonical
from p09c_ammo_catalog import MOUNTS, SHELLS
from p04g_crew_projection import SEAT_ROLES

SCHEMA = "p08b-profile13-battle.v1"
POLICY = {"id": "test_lab.profile13-stock-ap-free-repair.v1", "version": 1,
    "assemblies": ["ms1-stock", "is7-stock"], "shells": "owned-AP-only",
    "crew": "complete-actual-assigned", "equipment": "unsupported",
    "finish": "persist-actual-AP-and-terminal-HP-journal-free-instant-full-repair",
    "restart": "atomic-abort-refund-original-AP-free-full-repair",
    "credits": 0, "xp": 0, "per_shot_durability": False}
POLICY_SHA256 = sha(canonical(POLICY))
MAX_REPLY = 8192
COMMON = {"version", "operation", "account_id", "native_database_id", "command_key", "expected_revision", "run_id"}
EXTRA = {"run_open": set(), "inspect": set(), "admit": {"battle_id", "native_inventory_id"},
    "finish": {"battle_id", "native_inventory_id", "reservation_id", "remaining_ap", "terminal_hp", "reason"}}
REASONS = frozenset(("manual_leave", "battle_failure", "disconnect", "cancelled", "battle_finished"))
REJECTIONS = frozenset(("STALE_REVISION", "RUN_FENCED", "RUN_NOT_OPEN", "VEHICLE_RESERVED", "UNKNOWN_VEHICLE",
    "BATTLE_PROFILE_UNSUPPORTED", "INCOMPLETE_CREW", "AMMUNITION_EMPTY", "AMMUNITION_UNSUPPORTED",
    "RESERVATION_TERMINAL", "RESERVATION_MISMATCH", "DUPLICATE_PAYLOAD_MISMATCH", "INVALID_RESULT"))


def _uuid(value):
    require(type(value) is str and len(value) == 36, "INVALID_INPUT")
    try: parsed = uuid.UUID(value)
    except (ValueError, AttributeError): raise TransactionError("INVALID_INPUT")
    require(str(parsed) == value and parsed.version in (1, 2, 3, 4, 5), "INVALID_INPUT")
    return value


def _integer(value, low=0, high=2**31 - 1, code="INVALID_INPUT"):
    require(type(value) is int and low <= value <= high, code)
    return value


def validate_request(value, authenticated_account_id):
    require(type(value) is dict and type(value.get("operation")) is str and value["operation"] in EXTRA, "INVALID_INPUT")
    natural = value["operation"] == "finish" and value.get("reason") == "battle_finished"
    require(set(value) == COMMON | EXTRA[value["operation"]] | ({"results_json"} if natural else set())
        and type(value["version"]) is int and value["version"] == 1)
    _bounded_id(authenticated_account_id, "authenticated_account_id")
    require(value["account_id"] == authenticated_account_id, "FOREIGN_ACCOUNT")
    _bounded_id(value["account_id"], "account_id"); _bounded_id(value["command_key"], "command_key")
    require(re.fullmatch(r"[A-Za-z0-9_:-]{1,96}", value["command_key"]), "INVALID_INPUT")
    _integer(value["native_database_id"], 1); _revision(value["expected_revision"]); _uuid(value["run_id"])
    if value["operation"] in ("admit", "finish"):
        _integer(value["native_inventory_id"], 1)
        battle = value["battle_id"]
        require(type(battle) is str and battle.startswith(value["run_id"] + ":"), "INVALID_INPUT")
        suffix = battle[37:]
        require(re.fullmatch(r"[1-9][0-9]{0,19}", suffix) is not None and int(suffix) <= 2**64 - 1, "INVALID_INPUT")
    if value["operation"] == "finish":
        _bounded_id(value["reservation_id"], "reservation_id")
        _integer(value["remaining_ap"], 0, 96); _integer(value["terminal_hp"], 0, 100000)
        require(type(value["reason"]) is str and value["reason"] in REASONS, "INVALID_INPUT")
    if natural:
        require(type(value["results_json"]) is str and len(value["results_json"].encode("utf-8")) <= 32768, "INVALID_INPUT")
    require(len(canonical(value)) <= (65536 if natural else 2048), "INVALID_INPUT")
    return deepcopy(value)


def freeze_loadout(catalog, aggregate, native_inventory_id, *, available=True):
    """Authoritative exact-stock admission, reusable by the capability projection."""
    _integer(native_inventory_id, 1)
    owned = next((r for r in aggregate["research"]["vehicles"] if r["native_id"] == native_inventory_id), None)
    require(owned is not None, "UNKNOWN_VEHICLE")
    kind = {1: "ms1", 2: "is7"}.get(native_inventory_id)
    require(kind is not None, "BATTLE_PROFILE_UNSUPPORTED")
    mount = MOUNTS[kind + "-stock"]
    require(catalog.vehicles[owned["vehicle_id"]]["native_compact_id"] == mount.vehicle_native_compact_id
        and owned["modules"] == catalog.vehicles[owned["vehicle_id"]]["defaults"], "BATTLE_PROFILE_UNSUPPORTED")
    vehicle = next((r for r in aggregate["vehicles"] if r["vehicle_id"] == owned["vehicle_inventory_id"]), None)
    require(vehicle is not None, "CORRUPT_STORE")
    if available: require(vehicle["state"] == "available" and vehicle["battle_id"] is None, "VEHICLE_RESERVED")
    members = [r for r in aggregate["crew_inventory"]["members"] if r["vehicle_native_id"] == native_inventory_id]
    members.sort(key=lambda r: r["seat"])
    require(len(members) == len(SEAT_ROLES[native_inventory_id])
        and [r["seat"] for r in members] == list(range(len(members)))
        and [r["role"] for r in members] == list(SEAT_ROLES[native_inventory_id]), "INCOMPLETE_CREW")
    ammo = next((r for r in aggregate["ammunition"] if r["vehicle_id"] == owned["vehicle_inventory_id"]), None)
    require(ammo is not None and ammo["mount_id"] == mount.mount_id, "BATTLE_PROFILE_UNSUPPORTED")
    ap = "shell:" + mount.mount_id + "-ap"
    require(all(count == 0 for shell, count in ammo["loaded"].items() if shell != ap), "AMMUNITION_UNSUPPORTED")
    count = ammo["loaded"].get(ap, 0)
    require(type(count) is int and 1 <= count <= mount.capacity, "AMMUNITION_EMPTY")
    # P09E imports only plain assemblies, and explicitly checked empty source
    # equipment at migration. No runtime equipment is manufactured here.
    from p09e_research_projection import descriptor
    definition = catalog.vehicles[owned["vehicle_id"]]
    maximum = definition["hull_max_hp"] + definition["turret_max_hp"][owned["modules"]["turret"]]
    require(maximum == (90 if kind == "ms1" else 2150), "BATTLE_PROFILE_UNSUPPORTED")
    return {"kind": kind, "descriptor_hex": descriptor(catalog, owned).hex(),
        "native_inventory_id": native_inventory_id, "vehicle_inventory_id": owned["vehicle_inventory_id"],
        "ap_count": count, "shell_definition_id": ap, "shell_compact_id": SHELLS[ap].native_compact_id,
        "max_hp": maximum, "crew_ids": [r["crew_id"] for r in members]}


class BattleStore(ResearchStore):
    """One owner of profile13, hangar mutations, reservation and terminal result."""

    def __init__(self, path, catalog, *, failpoint=None):
        super().__init__(path, catalog, failpoint=failpoint)
        self._allow_prebattle = False
        self._hangar_mutation = False

    def _battle_schema(self):
        return self.connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='p08b_schema'").fetchone() is not None

    def initialize(self):
        super().initialize()
        if not self._battle_schema():
            require(self._allow_prebattle, "P08B_ACTIVATION_REQUIRED")
            return
        rows = self.connection.execute("SELECT version,policy_sha256,catalog_sha256 FROM p08b_schema").fetchall()
        require([tuple(r) for r in rows] == [(SCHEMA, POLICY_SHA256, self.catalog.sha256)], "UNSUPPORTED_BATTLE_SCHEMA")

    def activate(self, *, account_id, authenticated_account_id):
        require(account_id == authenticated_account_id, "FOREIGN_ACCOUNT")
        c = self.connection
        self._allow_prebattle = True
        c.execute("BEGIN IMMEDIATE")
        try:
            self.read_profile(account_id)
            if self._battle_schema():
                self.initialize(); c.commit(); return {"status": "already_active", "policy_sha256": POLICY_SHA256}
            c.execute("CREATE TABLE p08b_schema(version TEXT PRIMARY KEY,policy_sha256 TEXT NOT NULL,catalog_sha256 TEXT NOT NULL)")
            c.execute("INSERT INTO p08b_schema VALUES (?,?,?)", (SCHEMA, POLICY_SHA256, self.catalog.sha256))
            c.execute("""CREATE TABLE p08b_run(account_id TEXT NOT NULL REFERENCES game_snapshot(account_id),
                run_id TEXT NOT NULL,status TEXT NOT NULL CHECK(status IN ('active','retired')),
                PRIMARY KEY(account_id,run_id))""")
            c.execute("CREATE UNIQUE INDEX p08b_one_run ON p08b_run(account_id) WHERE status='active'")
            c.execute("""CREATE TABLE p08b_reservation(account_id TEXT NOT NULL,reservation_id TEXT NOT NULL,
                run_id TEXT NOT NULL,battle_id TEXT NOT NULL,native_inventory_id INTEGER NOT NULL,vehicle_inventory_id TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('active','finished','aborted_restart')),
                frozen_json TEXT NOT NULL,frozen_sha256 TEXT NOT NULL,source_revision INTEGER NOT NULL,
                admitted_revision INTEGER NOT NULL,result_json TEXT,result_sha256 TEXT,finished_revision INTEGER,
                PRIMARY KEY(account_id,reservation_id),UNIQUE(account_id,battle_id),
                FOREIGN KEY(account_id,run_id) REFERENCES p08b_run(account_id,run_id),
                FOREIGN KEY(account_id,vehicle_inventory_id) REFERENCES game_vehicle(account_id,vehicle_id),
                CHECK((status='active' AND result_json IS NULL AND result_sha256 IS NULL AND finished_revision IS NULL)
                    OR (status!='active' AND result_json IS NOT NULL AND result_sha256 IS NOT NULL AND finished_revision IS NOT NULL)))""")
            c.execute("CREATE UNIQUE INDEX p08b_one_reservation ON p08b_reservation(account_id) WHERE status='active'")
            self._failpoint("after_battle_schema")
            self.read_profile(account_id); self._failpoint("before_battle_activation_commit")
            c.commit()
            return {"status": "active", "policy_sha256": POLICY_SHA256}
        except Exception:
            c.rollback(); raise
        finally: self._allow_prebattle = False

    def _verified_snapshot(self, row, account):
        value = super()._verified_snapshot(row, account)
        if self._hangar_mutation:
            require(all(r["state"] == "available" for r in value["vehicles"]), "VEHICLE_RESERVED")
        if self._battle_schema(): self._verify_active(value)
        return value

    def _verify_active(self, aggregate):
        account = aggregate["account_id"]
        reserved = [r for r in aggregate["vehicles"] if r["state"] == "reserved"]
        active = self.connection.execute("SELECT * FROM p08b_reservation WHERE account_id=? AND status='active' LIMIT 2", (account,)).fetchall()
        require(len(active) == len(reserved) <= 1, "CORRUPT_STORE")
        if active:
            r = active[0]; value = self._reservation(r)
            require(reserved[0]["vehicle_id"] == r["vehicle_inventory_id"] and reserved[0]["battle_id"] == r["battle_id"], "CORRUPT_STORE")
            require(self._current_run(account) == r["run_id"] and value["frozen"] == freeze_loadout(self.catalog, aggregate, r["native_inventory_id"], available=False), "CORRUPT_STORE")

    def _current_run(self, account):
        rows = self.connection.execute("SELECT run_id FROM p08b_run WHERE account_id=? AND status='active' LIMIT 2", (account,)).fetchall()
        require(len(rows) <= 1, "CORRUPT_STORE")
        return rows[0][0] if rows else None

    def _reservation(self, row):
        require(row is not None, "RESERVATION_MISMATCH")
        from p09e_research_store import _json
        frozen = _json(row["frozen_json"])
        require(len(row["frozen_json"]) <= 4096 and sha(canonical(frozen)) == row["frozen_sha256"], "CORRUPT_STORE")
        require(set(frozen) == {"kind", "descriptor_hex", "native_inventory_id", "vehicle_inventory_id", "ap_count", "shell_definition_id", "shell_compact_id", "max_hp", "crew_ids"}, "CORRUPT_STORE")
        require(row["native_inventory_id"] == frozen["native_inventory_id"] and row["vehicle_inventory_id"] == frozen["vehicle_inventory_id"], "CORRUPT_STORE")
        kind = frozen["kind"]
        require(kind in ("ms1", "is7"), "CORRUPT_STORE")
        native, descriptor, maximum, capacity, shell = ((1, "010d1a000e00c90000001700170000", 90, 96, 2570) if kind == "ms1"
            else (2, "011c3a002400cd000b002f003a0000", 2150, 30, 14602))
        require(type(frozen["native_inventory_id"]) is int and frozen["native_inventory_id"] == native
            and frozen["descriptor_hex"] == descriptor and type(frozen["max_hp"]) is int and frozen["max_hp"] == maximum
            and type(frozen["ap_count"]) is int and 1 <= frozen["ap_count"] <= capacity
            and frozen["shell_definition_id"] == "shell:" + kind + "-stock-ap"
            and type(frozen["shell_compact_id"]) is int and frozen["shell_compact_id"] == shell
            and frozen["vehicle_inventory_id"] == row["account_id"] + (":starter-vehicle-v1" if native == 1 else ":test-is7-v1")
            and type(frozen["crew_ids"]) is list and len(frozen["crew_ids"]) == (2 if native == 1 else 5)
            and all(type(i) is str and 1 <= len(i) <= 96 and i.isascii() and i.startswith(row["account_id"] + ":") for i in frozen["crew_ids"])
            and len(set(frozen["crew_ids"])) == len(frozen["crew_ids"]), "CORRUPT_STORE")
        crew = self.connection.execute("SELECT crew_id,role FROM p04d_crew_member WHERE account_id=? UNION ALL SELECT crew_id,role FROM p04j_retired_member WHERE account_id=?", (row["account_id"], row["account_id"])).fetchall()
        by_id = {r["crew_id"]: r["role"] for r in crew}
        require(all(identity in by_id and by_id[identity] == role for identity, role in zip(frozen["crew_ids"], SEAT_ROLES[native])), "CORRUPT_STORE")
        result = None
        if row["status"] != "active":
            result = _json(row["result_json"])
            require(len(row["result_json"]) <= 2048 and sha(canonical(result)) == row["result_sha256"], "CORRUPT_STORE")
            require(set(result) == {"reason", "remaining_ap", "consumed_ap", "terminal_hp", "destroyed", "repaired_hp", "credits", "xp"}
                and result["reason"] in REASONS | {"aborted_restart"}
                and type(result["remaining_ap"]) is int and 0 <= result["remaining_ap"] <= frozen["ap_count"]
                and type(result["consumed_ap"]) is int and result["consumed_ap"] == frozen["ap_count"] - result["remaining_ap"]
                and ((result["reason"] == "aborted_restart" and result["terminal_hp"] is None and result["destroyed"] is None
                    and result["remaining_ap"] == frozen["ap_count"])
                    or (result["reason"] != "aborted_restart" and type(result["terminal_hp"]) is int and 0 <= result["terminal_hp"] <= frozen["max_hp"]
                        and type(result["destroyed"]) is bool and result["destroyed"] == (result["terminal_hp"] == 0)))
                and type(result["repaired_hp"]) is int and result["repaired_hp"] == frozen["max_hp"]
                and type(result["credits"]) is int and type(result["xp"]) is int and result["credits"] == result["xp"] == 0, "CORRUPT_STORE")
            require(row["finished_revision"] > row["admitted_revision"], "CORRUPT_STORE")
        else:
            require(row["result_json"] is None and row["result_sha256"] is None and row["finished_revision"] is None, "CORRUPT_STORE")
        require(row["admitted_revision"] == row["source_revision"] + 1, "CORRUPT_STORE")
        return {key: row[key] for key in ("reservation_id", "run_id", "battle_id", "native_inventory_id", "vehicle_inventory_id", "status")} | {
            "frozen": frozen, "frozen_sha256": row["frozen_sha256"], "result": result}

    def _guarded(self, function, *args, **kwargs):
        previous = self._hangar_mutation
        self._hangar_mutation = True
        try: return function(*args, **kwargs)
        finally: self._hangar_mutation = previous

    def execute(self, *args, **kwargs): return self._guarded(super().execute, *args, **kwargs)
    def service(self, *args, **kwargs): return self._guarded(super().service, *args, **kwargs)
    def _mutate(self, *args, **kwargs): return self._guarded(super()._mutate, *args, **kwargs)

    def publish(self, source, account_id, fixture_root):
        from pathlib import Path
        from p08b_battle_projection import BattleProjectionSource
        require(isinstance(source, BattleProjectionSource), "P08B_PROJECTION_REQUIRED")
        return super().publish(source, account_id, Path(fixture_root) / "p08b-v1")

    def _reply(self, request, revision, status, reservation=None, *, code=None, replayed=False):
        value = {key: request[key] for key in ("version", "operation", "account_id", "native_database_id", "command_key", "run_id")}
        value.update(source_revision=request["expected_revision"], revision=revision, status=status,
            replayed=replayed, code=code, reservation=reservation, policy_sha256=POLICY_SHA256)
        require(len(canonical(value)) <= MAX_REPLY, "PROFILE_TOO_LARGE")
        return value

    def _finish(self, request, aggregate, row, *, abort=False):
        value = self._reservation(row); frozen = value["frozen"]
        remaining, hp, reason = (frozen["ap_count"], None, "aborted_restart") if abort else (request["remaining_ap"], request["terminal_hp"], request["reason"])
        require(type(remaining) is int and 0 <= remaining <= frozen["ap_count"] and (abort or (type(hp) is int and 0 <= hp <= frozen["max_hp"])), "INVALID_RESULT")
        result = dict(reason=reason, remaining_ap=remaining, consumed_ap=frozen["ap_count"] - remaining,
            terminal_hp=hp, destroyed=None if abort else hp == 0, repaired_hp=frozen["max_hp"], credits=0, xp=0)
        c = self.connection; account = request["account_id"]
        mount = MOUNTS[frozen["kind"] + "-stock"]
        layout = self.layouts(account)[row["native_inventory_id"]]
        ammo = {key: remaining if key == frozen["shell_definition_id"] else 0 for key in sorted(mount.shell_ids)}
        require(c.execute("UPDATE p09c_ammo_mount SET loaded_json=? WHERE account_id=? AND vehicle_id=?", (canonical(ammo).decode("ascii"), account, row["vehicle_inventory_id"])).rowcount == 1, "CORRUPT_STORE")
        for index in (0, 2, 4): layout[index + 1] = remaining if abs(layout[index]) == frozen["shell_compact_id"] else 0
        require(c.execute("UPDATE p09d_native_layout SET layout_json=? WHERE account_id=? AND native_vehicle_id=?", (json.dumps(layout), account, row["native_inventory_id"])).rowcount == 1, "CORRUPT_STORE")
        require(c.execute("UPDATE game_vehicle SET state='available',battle_id=NULL WHERE account_id=? AND vehicle_id=? AND state='reserved' AND battle_id=?", (account, row["vehicle_inventory_id"], row["battle_id"])).rowcount == 1, "RESERVATION_MISMATCH")
        raw = canonical(result).decode("ascii")
        c.execute("UPDATE p08b_reservation SET status=?,result_json=?,result_sha256=?,finished_revision=? WHERE account_id=? AND reservation_id=?",
            ("aborted_restart" if abort else "finished", raw, sha(raw.encode("ascii")), aggregate["revision"] + 1, account, row["reservation_id"]))
        self._failpoint("after_battle_result")
        reservation = self._reservation(c.execute("SELECT * FROM p08b_reservation WHERE account_id=? AND reservation_id=?", (account, row["reservation_id"])).fetchone())
        if not abort and reason == "battle_finished": self._record_natural_result(request, reservation)
        return reservation

    def _record_natural_result(self, request, reservation):
        # Plain P08B has no results writer. Never acknowledge a natural finish
        # unless its subclass journals the full authoritative DTO atomically.
        raise TransactionError("P08C_RESULTS_REQUIRED")

    def _verify_natural_result(self, request, reservation):
        raise TransactionError("P08C_RESULTS_REQUIRED")

    def battle(self, request, *, authenticated_account_id):
        request = validate_request(request, authenticated_account_id)
        self.initialize(); c = self.connection
        account, key, operation = request["account_id"], request["command_key"], request["operation"]
        payload_sha = sha(canonical({"schema": SCHEMA, "policy_sha256": POLICY_SHA256, "request": request}))
        command = SCHEMA + ":" + operation
        c.execute("BEGIN IMMEDIATE" if operation != "inspect" else "BEGIN")
        try:
            aggregate = self.read_profile(account); revision = aggregate["revision"]
            require(self._project_profile(account, aggregate)["native_database_id"] == request["native_database_id"], "FOREIGN_ACCOUNT")
            current_run = self._current_run(account)
            seen_run = c.execute("SELECT status FROM p08b_run WHERE account_id=? AND run_id=?", (account, request["run_id"])).fetchone()
            if operation != "inspect":
                if operation == "run_open": require(seen_run is None or seen_run[0] == "active", "RUN_FENCED")
                else: require(current_run is not None, "RUN_NOT_OPEN"); require(current_run == request["run_id"], "RUN_FENCED")
            ledger = c.execute("SELECT * FROM game_command_ledger WHERE account_id=? AND command_id=?", (account, key)).fetchone()
            if ledger is not None and operation != "inspect":
                require(ledger["command_type"] == command and ledger["payload_sha256"] == payload_sha, "DUPLICATE_PAYLOAD_MISMATCH")
                from p09e_research_store import _json
                journal = _json(ledger["result_json"])
                require(sha(canonical(journal)) == ledger["p09c_result_sha256"] and set(journal) == {"schema", "request", "response"}
                    and journal["schema"] == SCHEMA and journal["request"] == request, "CORRUPT_STORE")
                response = journal["response"]
                require(response["source_revision"] == ledger["source_revision"] == request["expected_revision"]
                    and response["revision"] == ledger["destination_revision"] <= revision
                    and response["replayed"] is False, "CORRUPT_STORE")
                saved_reservation = response.get("reservation")
                if saved_reservation is not None:
                    saved_row = c.execute("SELECT * FROM p08b_reservation WHERE account_id=? AND reservation_id=?", (account, saved_reservation.get("reservation_id"))).fetchone()
                    require(saved_row is not None, "CORRUPT_STORE")
                    if operation != "admit": require(self._reservation(saved_row) == saved_reservation, "CORRUPT_STORE")
                if operation == "finish":
                    require(saved_reservation is not None and saved_reservation["status"] == "finished"
                        and saved_reservation["run_id"] == request["run_id"] and saved_reservation["battle_id"] == request["battle_id"]
                        and saved_reservation["reservation_id"] == request["reservation_id"] and saved_reservation["native_inventory_id"] == request["native_inventory_id"]
                        and all(saved_reservation["result"][field] == request[field] for field in ("reason", "remaining_ap", "terminal_hp"))
                        and saved_row["finished_revision"] == ledger["destination_revision"], "CORRUPT_STORE")
                    if request["reason"] == "battle_finished": self._verify_natural_result(request, saved_reservation)
                elif operation == "run_open" and saved_reservation is not None:
                    require(saved_reservation["status"] == "aborted_restart" and saved_reservation["run_id"] != request["run_id"]
                        and saved_row["finished_revision"] == ledger["destination_revision"], "CORRUPT_STORE")
                require(response == self._reply(request, ledger["destination_revision"], {"run_open": "ready", "admit": "admitted", "finish": "finished"}[operation], saved_reservation)
                    and ledger["destination_revision"] in ((ledger["source_revision"], ledger["source_revision"] + 1) if operation == "run_open" else (ledger["source_revision"] + 1,)), "CORRUPT_STORE")
                if operation == "admit":
                    row = c.execute("SELECT * FROM p08b_reservation WHERE account_id=? AND reservation_id=?", (account, key)).fetchone()
                    require(row is not None and row["status"] == "active", "RESERVATION_TERMINAL")
                    require(self._reservation(row) == response["reservation"], "CORRUPT_STORE")
                response = dict(response, replayed=True)
                require(len(canonical(response)) <= MAX_REPLY, "CORRUPT_STORE")
                c.commit(); return response
            if operation == "inspect":
                row = c.execute("SELECT * FROM p08b_reservation WHERE account_id=? AND status='active'", (account,)).fetchone()
                result = self._reply(request, revision, "inspected", self._reservation(row) if row else None)
                c.commit(); return result
            require(revision == request["expected_revision"], "STALE_REVISION")
            require(revision < 2**31 - 1, "REVISION_EXHAUSTED")
            public_before = c.execute("SELECT profile_json FROM game_profiles WHERE account_id=?", (account,)).fetchone()[0]
            active = c.execute("SELECT * FROM p08b_reservation WHERE account_id=? AND status='active'", (account,)).fetchone()
            reservation = None; destination = revision + 1
            if operation == "run_open":
                if current_run == request["run_id"]:
                    destination = revision
                else:
                    if active: reservation = self._finish(request, aggregate, active, abort=True)
                    c.execute("UPDATE p08b_run SET status='retired' WHERE account_id=? AND status='active'", (account,))
                    c.execute("INSERT INTO p08b_run VALUES (?,?,'active')", (account, request["run_id"]))
                    self._failpoint("after_battle_run")
                status = "ready"
            elif operation == "admit":
                require(active is None, "VEHICLE_RESERVED")
                require(c.execute("SELECT 1 FROM p08b_reservation WHERE account_id=? AND battle_id=?", (account, request["battle_id"])).fetchone() is None, "RESERVATION_TERMINAL")
                frozen = freeze_loadout(self.catalog, aggregate, request["native_inventory_id"])
                raw = canonical(frozen).decode("ascii")
                c.execute("UPDATE game_vehicle SET state='reserved',battle_id=? WHERE account_id=? AND vehicle_id=?", (request["battle_id"], account, frozen["vehicle_inventory_id"]))
                self._failpoint("after_battle_vehicle")
                c.execute("INSERT INTO p08b_reservation VALUES (?,?,?,?,?,?,'active',?,?,?,?,NULL,NULL,NULL)",
                    (account, key, request["run_id"], request["battle_id"], request["native_inventory_id"], frozen["vehicle_inventory_id"], raw, sha(raw.encode("ascii")), revision, destination))
                reservation = self._reservation(c.execute("SELECT * FROM p08b_reservation WHERE account_id=? AND reservation_id=?", (account, key)).fetchone())
                self._failpoint("after_battle_reservation"); status = "admitted"
            else:
                row = c.execute("SELECT * FROM p08b_reservation WHERE account_id=? AND reservation_id=?", (account, request["reservation_id"])).fetchone()
                require(row is not None and row["run_id"] == request["run_id"] and row["battle_id"] == request["battle_id"]
                    and row["native_inventory_id"] == request["native_inventory_id"], "RESERVATION_MISMATCH")
                require(row["status"] == "active", "RESERVATION_TERMINAL")
                reservation = self._finish(request, aggregate, row); status = "finished"
            if destination != revision: self._save_crew_projection(account, destination, public_before)
            response = self._reply(request, destination, status, reservation)
            journal = canonical({"schema": SCHEMA, "request": request, "response": response}).decode("ascii")
            require(len(journal) <= (65536 if request.get("reason") == "battle_finished" else MAX_REPLY), "PROFILE_TOO_LARGE")
            c.execute("INSERT INTO game_command_ledger VALUES (?,?,?,?,?,?,?,?)", (account, key, command, payload_sha, revision, destination, journal, sha(journal.encode("ascii"))))
            self._failpoint("after_battle_ledger"); self.read_profile(account); self._failpoint("before_battle_commit")
            c.commit(); return response
        except Exception:
            c.rollback(); raise
