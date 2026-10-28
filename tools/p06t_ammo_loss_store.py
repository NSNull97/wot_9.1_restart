"""Explicit v4 ammo-rack loss authority beside unchanged mixed-v2 records.

Only the configured gateway may supply causal terminal facts. Three loaded
stacks include the clip; depot inventory and accepted-shot counters are never
invented here. Old rows retain their original contract and hashes.
"""
from copy import deepcopy
import re

from game_profile_tx import TransactionError, _bounded_id, _revision
from p09d_ammo_store import require, sha
from p09d_ammo_projection import canonical
from p09e_research_store import _json
from p08b_battle_store import _uuid, _integer, REASONS, MAX_PARTICIPANTS, MAX_RESULT_REQUEST
# RES-30: shots/device journal of a 30-actor battle (gateway MAX_BATTLE_SHOTS, MAX_DAMAGE_EVENTS).
MAX_BATTLE_SHOTS = MAX_PARTICIPANTS * 160
MAX_DEVICE_SEQUENCE = MAX_BATTLE_SHOTS * 16
from p08c_battle_results import results_value
from p06t_mixed_store import MixedAmmoStore, POLICY_SHA256 as BASE_POLICY_SHA256, SOURCE_SHA256
from p06t_terminal import MANIFEST_SHA256

VERSION = 4
CONTRACT = "p06t-ammo-rack-loss.v1"
SCHEMA = "battle-ammo-loss.v1"
POLICY = {"id": "test_lab.profile13-stock-mixed-ammo-rack-loss.v1", "version": 1,
    "base_mixed_policy_sha256": BASE_POLICY_SHA256, "shell_catalog_sha256": SOURCE_SHA256,
    "terminal_manifest_sha256": MANIFEST_SHA256,
    "trigger": "authoritative-ammoBay-positive-to-zero-with-positive-loaded-ammunition",
    "loss": "all-remaining-three-loaded-stacks-including-clip-depot-unchanged",
    "empty_bay": "no-detonation-no-ammunition-loss-no-extra-hull-damage",
    "accounting": "frozen-equals-fired-plus-lost-plus-remaining-per-source-stack",
    "shots": "accepted-shoot-only-sum-fired", "finish": "atomic-terminal-accounting-and-full-results-free-full-repair",
    "restart": "uncommitted-active-reserve-refunds-original-three-stacks-once-unknown-terminal",
    "per_shot_durability": False, "credits": 0, "xp": 0}
POLICY_SHA256 = sha(canonical(POLICY))
TABLES = {"battle_ammo_loss_schema", "battle_ammo_loss_owner", "battle_ammo_loss_reservation"}
COMMON = {"version", "contract", "operation", "account_id", "native_database_id", "command_key", "expected_revision", "run_id"}
EXTRA = {"run_open": set(), "inspect": set(), "admit": {"battle_id", "native_inventory_id"},
    "finish": {"battle_id", "native_inventory_id", "reservation_id", "remaining_ammunition", "fired_ammunition",
        "lost_ammunition", "loss_event", "terminal_hp", "reason", "terminal_state_json"}}
REJECTIONS = frozenset({"STALE_REVISION", "RUN_FENCED", "RUN_NOT_OPEN", "VEHICLE_RESERVED", "UNKNOWN_VEHICLE",
    "BATTLE_PROFILE_UNSUPPORTED", "OWNER_ACCEPTANCE_REQUIRED", "INCOMPLETE_CREW", "AMMUNITION_EMPTY", "AMMUNITION_UNSUPPORTED",
    "RESERVATION_TERMINAL", "RESERVATION_MISMATCH", "DUPLICATE_PAYLOAD_MISMATCH", "INVALID_RESULT", "RESULT_MISMATCH",
    "INVALID_TERMINAL_STATE", "AMMO_LOSS_POLICY_REQUIRED", "AMMO_LOSS_WRONG_ACTIVE_CONTRACT"})
MAX_REPLY = 8192


def _namespace(connection):
    names = {r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'battle_ammo_loss_%'")}
    require(not names or names == TABLES, "UNSUPPORTED_AMMO_LOSS_SCHEMA")
    if names:
        rows = connection.execute("SELECT version,policy_sha256,base_policy_sha256,source_sha256,terminal_sha256,catalog_sha256 FROM battle_ammo_loss_schema").fetchall()
        require(len(rows) == 1 and tuple(rows[0])[:5] == (SCHEMA, POLICY_SHA256, BASE_POLICY_SHA256, SOURCE_SHA256, MANIFEST_SHA256)
            and type(rows[0][5]) is str and re.fullmatch(r"[0-9a-f]{64}", rows[0][5]), "UNSUPPORTED_AMMO_LOSS_SCHEMA")
    return bool(names)


def loss_owner(connection, account_id):
    """Read-only fence for trusted existing writer/factory entry points."""
    if not _namespace(connection): return False
    row = connection.execute("SELECT policy_sha256,activated_revision FROM battle_ammo_loss_owner WHERE account_id=?", (account_id,)).fetchone()
    if row is None:
        require(connection.execute("SELECT 1 FROM battle_ammo_loss_reservation WHERE account_id=? LIMIT 1",(account_id,)).fetchone() is None,"UNSUPPORTED_AMMO_LOSS_SCHEMA")
        return False
    require(row[0] == POLICY_SHA256 and type(row[1]) is int and 13<=row[1]<2**31, "UNSUPPORTED_AMMO_LOSS_SCHEMA")
    return True


def require_loss_compatible(connection, account_id, *, contract=None):
    active = loss_owner(connection, account_id)
    require(not active or contract == CONTRACT, "AMMO_LOSS_POLICY_REQUIRED")
    return active


def _rows(value):
    require(type(value) is list and len(value) == 3, "INVALID_INPUT")
    for row in value:
        require(type(row) is dict and set(row) == {"shell_compact_id", "count"}, "INVALID_INPUT")
        _integer(row["shell_compact_id"], 1, 65535); _integer(row["count"], 0, 160)


def _event(value):
    if value is None: return
    require(type(value) is dict and set(value) == {"shot", "attacker_slot", "target_slot", "tick", "device_sequence"}, "INVALID_INPUT")
    _integer(value["shot"], 1, MAX_BATTLE_SHOTS)
    _integer(value["attacker_slot"], 0, MAX_PARTICIPANTS - 1); _integer(value["target_slot"], 0, MAX_PARTICIPANTS - 1)
    _integer(value["tick"], 1000, 216000); _integer(value["device_sequence"], 1, MAX_DEVICE_SEQUENCE)
    require(value["attacker_slot"] != value["target_slot"], "INVALID_INPUT")


def validate_request(value, account):
    require(type(value) is dict and type(value.get("operation")) is str and value["operation"] in EXTRA, "INVALID_INPUT")
    natural = value["operation"] == "finish" and value.get("reason") == "battle_finished"
    require(set(value) == COMMON | EXTRA[value["operation"]] | ({"results_json"} if natural else set())
        and type(value["version"]) is int and value["version"] == VERSION and value["contract"] == CONTRACT, "INVALID_INPUT")
    require(value["account_id"] == account, "FOREIGN_ACCOUNT"); _uuid(account); _uuid(value["run_id"])
    _bounded_id(value["command_key"], "command_key"); _integer(value["native_database_id"], 1); _revision(value["expected_revision"])
    require(re.fullmatch(r"[A-Za-z0-9_:-]{1,96}", value["command_key"]), "INVALID_INPUT")
    if value["operation"] in ("admit", "finish"):
        _integer(value["native_inventory_id"], 1)
        battle = value["battle_id"]
        require(type(battle) is str and battle.startswith(value["run_id"] + ":"), "INVALID_INPUT")
        tail = battle[37:]
        require(re.fullmatch(r"[1-9][0-9]{0,19}", tail) and int(tail) <= 2**64-1, "INVALID_INPUT")
    if value["operation"] == "finish":
        _bounded_id(value["reservation_id"], "reservation_id"); _integer(value["terminal_hp"], 0, 10000)
        require(type(value["reason"]) is str and value["reason"] in REASONS, "INVALID_INPUT")
        for name in ("remaining_ammunition", "fired_ammunition", "lost_ammunition"): _rows(value[name])
        _event(value["loss_event"])
        require(type(value["terminal_state_json"]) is str and len(value["terminal_state_json"].encode("utf8")) <= 8192, "INVALID_INPUT")
        value = dict(value, terminal_state_json=canonical(_json(value["terminal_state_json"])).decode("ascii"))
    if natural:
        value = dict(value, results_json=canonical(results_value(value["results_json"])).decode("ascii"))
    require(len(canonical(value)) <= (MAX_RESULT_REQUEST if natural else 16384 if value["operation"] == "finish" else 2048), "INVALID_INPUT")
    return deepcopy(value)


def validate_results_request(value, account):
    require(type(value) is dict and set(value) == {"version", "contract", "operation", "account_id", "native_database_id", "command_key", "arena_id"}
        and type(value["version"]) is int and value["version"] == VERSION and value["contract"] == CONTRACT
        and type(value["operation"]) is str and value["operation"] in ("query", "ack"), "INVALID_INPUT")
    require(value["account_id"] == account, "FOREIGN_ACCOUNT"); _uuid(account)
    _integer(value["native_database_id"], 1); _bounded_id(value["command_key"], "command_key")
    require(re.fullmatch(r"[A-Za-z0-9_:-]{1,96}", value["command_key"]), "INVALID_INPUT")
    arena = value["arena_id"]
    require(type(arena) is str and re.fullmatch(r"[1-9][0-9]{0,18}", arena) and int(arena) <= 2**63-1 and len(canonical(value)) <= 2048, "INVALID_INPUT")
    return deepcopy(value)


class AmmoLossStore(MixedAmmoStore):
    AMMO_LOSS_CONTRACT = CONTRACT

    def publish(self, source, account_id, fixture_root):
        if not self.loss_active(): return super().publish(source, account_id, fixture_root)
        from pathlib import Path
        from p04m_pool_projection import PoolProjectionSource
        from p08b_battle_store import BattleStore
        if not isinstance(source, PoolProjectionSource): source = PoolProjectionSource(source, self)
        return BattleStore.publish(self, AmmoLossProjectionSource(source, self), account_id, Path(fixture_root) / "p06t-loss-v1")

    def loss_active(self):
        active = loss_owner(self.connection, self.pool_account)
        if _namespace(self.connection):
            require(self.connection.execute("SELECT catalog_sha256 FROM battle_ammo_loss_schema").fetchone()[0] == self.catalog.sha256, "UNSUPPORTED_AMMO_LOSS_SCHEMA")
        return active

    def activate_loss(self, *, account_id, authenticated_account_id, expected_revision, native_database_id):
        require(account_id == authenticated_account_id == self.pool_account, "FOREIGN_ACCOUNT")
        _uuid(account_id); _revision(expected_revision); _integer(native_database_id,1)
        c = self.connection; c.execute("BEGIN IMMEDIATE")
        try:
            aggregate = self.read_profile(account_id)
            require(self.mixed_active(), "P06T_ACTIVATION_REQUIRED")
            require(aggregate["revision"] == expected_revision, "STALE_REVISION")
            require(self._project_profile(account_id, aggregate)["native_database_id"] == native_database_id, "FOREIGN_ACCOUNT")
            require(not self._active_mixed(account_id) and c.execute("SELECT 1 FROM p08b_reservation WHERE account_id=? AND status='active'", (account_id,)).fetchone() is None
                and all(v["state"] == "available" for v in aggregate["vehicles"]), "VEHICLE_RESERVED")
            if not _namespace(c):
                c.execute("CREATE TABLE battle_ammo_loss_schema(version TEXT PRIMARY KEY,policy_sha256 TEXT NOT NULL,base_policy_sha256 TEXT NOT NULL,source_sha256 TEXT NOT NULL,terminal_sha256 TEXT NOT NULL,catalog_sha256 TEXT NOT NULL)")
                c.execute("INSERT INTO battle_ammo_loss_schema VALUES (?,?,?,?,?,?)", (SCHEMA, POLICY_SHA256, BASE_POLICY_SHA256, SOURCE_SHA256, MANIFEST_SHA256, self.catalog.sha256))
                c.execute("CREATE TABLE battle_ammo_loss_owner(account_id TEXT PRIMARY KEY REFERENCES p06t_owner(account_id),policy_sha256 TEXT NOT NULL,activated_revision INTEGER NOT NULL)")
                c.execute("""CREATE TABLE battle_ammo_loss_reservation(account_id TEXT NOT NULL,reservation_id TEXT NOT NULL,policy_sha256 TEXT NOT NULL,
                    wrapper_json TEXT NOT NULL,wrapper_sha256 TEXT NOT NULL,result_json TEXT,result_sha256 TEXT,
                    PRIMARY KEY(account_id,reservation_id),FOREIGN KEY(account_id) REFERENCES battle_ammo_loss_owner(account_id),
                    FOREIGN KEY(account_id,reservation_id) REFERENCES p06t_reservation(account_id,reservation_id),
                    CHECK((result_json IS NULL AND result_sha256 IS NULL) OR (result_json IS NOT NULL AND result_sha256 IS NOT NULL)))""")
            self._failpoint("after_ammo_loss_schema")
            c.execute("INSERT OR IGNORE INTO battle_ammo_loss_owner VALUES (?,?,?)", (account_id, POLICY_SHA256, aggregate["revision"]))
            require(self.loss_active(), "AMMO_LOSS_POLICY_REQUIRED")
            self._failpoint("before_ammo_loss_activation_commit"); c.commit()
            return dict(version=VERSION, contract=CONTRACT, status="active", account_id=account_id, policy_sha256=POLICY_SHA256, ammunition_granted=0)
        except Exception: c.rollback(); raise

    @staticmethod
    def _wrapper(base):
        return dict(policy_sha256=POLICY_SHA256, loadout=base["frozen"], loadout_sha256=base["frozen_sha256"])

    def _accounting(self, frozen, remaining, fired, lost, event, hp, reason, terminal_state, *, abort=False):
        for rows in (remaining, fired, lost): _rows(rows)
        _event(event)
        for initial, a, b, d in zip(frozen["ammunition"], remaining, fired, lost):
            require(all(r["shell_compact_id"] == initial["shell_compact_id"] for r in (a, b, d))
                and a["count"] + b["count"] + d["count"] == initial["count"], "INVALID_RESULT")
        # Retain the unchanged v2 terminal/source validator internally. Its
        # consumed means removed total here; returned v4 fields are unambiguous.
        base = super()._terminal(frozen, remaining, hp, reason, terminal_state=terminal_state, abort=abort)
        if abort:
            require(event is None and not any(r["count"] for r in fired + lost), "INVALID_RESULT")
        elif event is None:
            require(not any(r["count"] for r in lost), "INVALID_RESULT")
        else:
            state = base["terminal_state"]; death = state["death"]
            bay = next((r for r in state["devices"] if r["extra_index"] == 27), None)
            require(sum(r["count"] for r in lost) > 0 and not any(r["count"] for r in remaining)
                and hp == 0 and bay is not None and bay["health"] == 0 and reason != "cancelled"
                and event["attacker_slot"] < state["roster_size"] and event["target_slot"] < state["roster_size"]
                and death["killer_slot"] == event["attacker_slot"] and death["tick"] == event["tick"], "INVALID_RESULT")
        if reason == "cancelled":
            require(event is None and not any(r["count"] for r in fired + lost) and hp == frozen["max_hp"], "INVALID_RESULT")
        result = {k: v for k, v in base.items() if k != "consumed_ammunition"}
        return dict(result, fired_ammunition=deepcopy(fired), lost_ammunition=deepcopy(lost), loss_event=deepcopy(event))

    def _loss_reservation(self, row):
        base = super()._mixed_reservation(row)
        side = self.connection.execute("SELECT * FROM battle_ammo_loss_reservation WHERE account_id=? AND reservation_id=?", (row["account_id"], row["reservation_id"])).fetchone()
        require(side is not None and side["policy_sha256"] == POLICY_SHA256, "AMMO_LOSS_WRONG_ACTIVE_CONTRACT")
        wrapper = self._wrapper(base)
        require(len(side["wrapper_json"]) <= 6144 and _json(side["wrapper_json"]) == wrapper and sha(canonical(wrapper)) == side["wrapper_sha256"], "CORRUPT_STORE")
        result = None
        if base["result"] is None:
            require(side["result_json"] is None and side["result_sha256"] is None, "CORRUPT_STORE")
        else:
            result = _json(side["result_json"])
            require(len(side["result_json"]) <= 6144 and sha(canonical(result)) == side["result_sha256"], "CORRUPT_STORE")
            expected = self._accounting(base["frozen"], result["remaining_ammunition"], result["fired_ammunition"], result["lost_ammunition"],
                result["loss_event"], result["terminal_hp"], result["reason"], result["terminal_state"], abort=base["status"] == "aborted_restart")
            require(result == expected and all(result[k] == value for k, value in base["result"].items() if k != "consumed_ammunition"), "CORRUPT_STORE")
        return {k: v for k, v in base.items() if k not in ("frozen", "frozen_sha256", "result")} | dict(frozen=wrapper, frozen_sha256=side["wrapper_sha256"], result=result)

    def _finish_loss(self, request, aggregate, row, *, abort=False):
        previous = self._loss_reservation(row); frozen = previous["frozen"]["loadout"]
        initial = [dict(shell_compact_id=r["shell_compact_id"], count=r["count"]) for r in frozen["ammunition"]]
        zeros = [dict(r, count=0) for r in initial]
        remaining = initial if abort else request["remaining_ammunition"]
        result = self._accounting(frozen, remaining, zeros if abort else request["fired_ammunition"], zeros if abort else request["lost_ammunition"],
            None if abort else request["loss_event"], None if abort else request["terminal_hp"], "aborted_restart" if abort else request["reason"],
            None if abort else _json(request["terminal_state_json"]), abort=abort)
        raw = canonical(result)
        self.connection.execute("UPDATE battle_ammo_loss_reservation SET result_json=?,result_sha256=? WHERE account_id=? AND reservation_id=?",
            (raw.decode("ascii"), sha(raw), row["account_id"], row["reservation_id"]))
        self._failpoint("after_ammo_loss_accounting")
        super()._finish_mixed(request, aggregate, row, abort=abort)
        return self._loss_reservation(self.connection.execute("SELECT * FROM p06t_reservation WHERE account_id=? AND reservation_id=?", (row["account_id"], row["reservation_id"])).fetchone())

    def _match_mixed_result(self, value, reservation, native, arena):
        account = reservation["frozen"]["vehicle_inventory_id"][:36]
        side = self.connection.execute("SELECT 1 FROM battle_ammo_loss_reservation WHERE account_id=? AND reservation_id=?", (account, reservation["reservation_id"])).fetchone() if _namespace(self.connection) else None
        if side is None: return super()._match_mixed_result(value, reservation, native, arena)
        row = self.connection.execute("SELECT * FROM p06t_reservation WHERE account_id=? AND reservation_id=?", (account, reservation["reservation_id"])).fetchone()
        receipt = self._loss_reservation(row); f = receipt["frozen"]["loadout"]; terminal = receipt["result"]
        own = next((p for p in value["participants"] if p["account_dbid"] == native), None)
        require(value["arena_id"] == int(arena) and own is not None and own["type_compact_descr"] == self.registry.profiles[f["kind"]].type_compact_id
            and own["health"] == terminal["terminal_hp"] and own["shots"] == sum(r["count"] for r in terminal["fired_ammunition"]), "RESULT_MISMATCH")
        state = self.terminal_policy.validate(canonical(terminal["terminal_state"]).decode("ascii"), frozen=f, terminal_hp=terminal["terminal_hp"], results=value)
        killer = state["death"]["killer_slot"]
        require(own["death_reason"] == state["death"]["reason"] and own["killer_id"] == (0 if killer is None else value["participants"][killer]["vehicle_id"]), "RESULT_MISMATCH")
        event = terminal["loss_event"]
        if event is not None:
            require(value["participants"][event["target_slot"]]["account_dbid"] == native
                and event["shot"] <= sum(p["shots"] for p in value["participants"]), "RESULT_MISMATCH")

    def _loss_reply(self, request, revision, status, reservation=None, *, code=None, replayed=False):
        value = {k: request[k] for k in COMMON}
        value.update(status=status, source_revision=request["expected_revision"], revision=revision, replayed=replayed,
            code=code, reservation=reservation, legacy_reservation=None, policy_sha256=POLICY_SHA256)
        value.pop("expected_revision")
        require(len(canonical(value)) <= MAX_REPLY, "PROFILE_TOO_LARGE")
        return value

    def battle(self, request, *, authenticated_account_id):
        if type(request) is dict and request.get("version") == VERSION:
            return self.battle_loss(request, authenticated_account_id=authenticated_account_id)
        require(not self.loss_active(), "AMMO_LOSS_POLICY_REQUIRED")
        return super().battle(request, authenticated_account_id=authenticated_account_id)

    def battle_loss(self, request, *, authenticated_account_id):
        request = validate_request(request, authenticated_account_id)
        account, key, operation = request["account_id"], request["command_key"], request["operation"]
        require(account == self.pool_account and self.loss_active(), "AMMO_LOSS_POLICY_REQUIRED")
        c = self.connection; c.execute("BEGIN" if operation == "inspect" else "BEGIN IMMEDIATE")
        try:
            aggregate = self.read_profile(account); revision = aggregate["revision"]
            require(self._project_profile(account, aggregate)["native_database_id"] == request["native_database_id"], "FOREIGN_ACCOUNT")
            current = self._current_run(account)
            active = self._active_mixed(account)
            old = c.execute("SELECT 1 FROM p08b_reservation WHERE account_id=? AND status='active'", (account,)).fetchone()
            require(old is None and all(c.execute("SELECT 1 FROM battle_ammo_loss_reservation WHERE account_id=? AND reservation_id=?", (account, r["reservation_id"])).fetchone() for r in active), "AMMO_LOSS_WRONG_ACTIVE_CONTRACT")
            seen = c.execute("SELECT status FROM p08b_run WHERE account_id=? AND run_id=?", (account, request["run_id"])).fetchone()
            if operation != "inspect":
                if operation == "run_open": require(seen is None or seen[0] == "active", "RUN_FENCED")
                else: require(current is not None, "RUN_NOT_OPEN"); require(current == request["run_id"], "RUN_FENCED")
            payload = sha(canonical(dict(schema=SCHEMA, policy_sha256=POLICY_SHA256, request=request))); command = SCHEMA + ":" + operation
            ledger = c.execute("SELECT * FROM game_command_ledger WHERE account_id=? AND command_id=?", (account, key)).fetchone()
            if ledger is not None and operation != "inspect":
                require(ledger["command_type"] == command and ledger["payload_sha256"] == payload, "DUPLICATE_PAYLOAD_MISMATCH")
                journal = _json(ledger["result_json"])
                require(sha(canonical(journal)) == ledger["p09c_result_sha256"] and set(journal) == {"schema", "request", "response"}
                    and journal["schema"] == SCHEMA and journal["request"] == request, "CORRUPT_STORE")
                saved = journal["response"]; receipt = saved["reservation"]
                require(saved["source_revision"] == ledger["source_revision"] == request["expected_revision"] and saved["revision"] == ledger["destination_revision"] <= revision, "CORRUPT_STORE")
                if receipt is not None:
                    row = c.execute("SELECT * FROM p06t_reservation WHERE account_id=? AND reservation_id=?", (account, receipt["reservation_id"])).fetchone()
                    if operation == "admit": require(row is not None and row["status"] == "active", "RESERVATION_TERMINAL")
                    require(self._loss_reservation(row) == receipt, "CORRUPT_STORE")
                require(saved == self._loss_reply(request, ledger["destination_revision"], {"run_open": "ready", "admit": "admitted", "finish": "finished"}[operation], receipt), "CORRUPT_STORE")
                if operation == "finish" and request["reason"] == "battle_finished": self._read_mixed_result(account, request["native_database_id"], request["battle_id"].rsplit(":", 1)[1])
                c.commit(); return dict(saved, replayed=True)
            if operation == "inspect":
                reply = self._loss_reply(request, revision, "inspected", self._loss_reservation(active[0]) if active else None)
                c.commit(); return reply
            require(revision == request["expected_revision"], "STALE_REVISION"); require(revision < 2**31-1, "REVISION_EXHAUSTED")
            public = c.execute("SELECT profile_json FROM game_profiles WHERE account_id=?", (account,)).fetchone()[0]
            receipt, destination = None, revision + 1
            if operation == "run_open":
                if current == request["run_id"]: destination = revision
                else:
                    if active: receipt = self._finish_loss(request, aggregate, active[0], abort=True)
                    c.execute("UPDATE p08b_run SET status='retired' WHERE account_id=? AND status='active'", (account,))
                    c.execute("INSERT INTO p08b_run VALUES (?,?,'active')", (account, request["run_id"]))
                    self._failpoint("after_ammo_loss_run")
                status = "ready"
            elif operation == "admit":
                require(not active, "VEHICLE_RESERVED")
                require(c.execute("SELECT 1 FROM p06t_reservation WHERE account_id=? AND battle_id=?", (account, request["battle_id"])).fetchone() is None
                    and c.execute("SELECT 1 FROM p08b_reservation WHERE account_id=? AND battle_id=?", (account, request["battle_id"])).fetchone() is None, "RESERVATION_TERMINAL")
                frozen = self.freeze_mixed(aggregate, request["native_inventory_id"]); raw = canonical(frozen)
                require(c.execute("UPDATE game_vehicle SET state='reserved',battle_id=? WHERE account_id=? AND vehicle_id=? AND state='available'", (request["battle_id"], account, frozen["vehicle_inventory_id"])).rowcount == 1, "VEHICLE_RESERVED")
                self._failpoint("after_ammo_loss_vehicle")
                c.execute("INSERT INTO p06t_reservation VALUES (?,?,?,?,?,?,'active',?,?,?,?,NULL,NULL,NULL)", (account, key, request["run_id"], request["battle_id"], request["native_inventory_id"], frozen["vehicle_inventory_id"], raw.decode("ascii"), sha(raw), revision, destination))
                base = super()._mixed_reservation(c.execute("SELECT * FROM p06t_reservation WHERE account_id=? AND reservation_id=?", (account, key)).fetchone())
                wrapper = canonical(self._wrapper(base))
                c.execute("INSERT INTO battle_ammo_loss_reservation VALUES (?,?,?,?,?,NULL,NULL)", (account, key, POLICY_SHA256, wrapper.decode("ascii"), sha(wrapper)))
                self._failpoint("after_ammo_loss_reservation")
                receipt = self._loss_reservation(c.execute("SELECT * FROM p06t_reservation WHERE account_id=? AND reservation_id=?", (account, key)).fetchone()); status = "admitted"
            else:
                row = c.execute("SELECT * FROM p06t_reservation WHERE account_id=? AND reservation_id=?", (account, request["reservation_id"])).fetchone()
                require(row is not None and row["run_id"] == request["run_id"] and row["battle_id"] == request["battle_id"] and row["native_inventory_id"] == request["native_inventory_id"], "RESERVATION_MISMATCH")
                require(row["status"] == "active", "RESERVATION_TERMINAL")
                receipt = self._finish_loss(request, aggregate, row); status = "finished"
            if destination != revision: self._save_crew_projection(account, destination, public)
            response = self._loss_reply(request, destination, status, receipt)
            raw = canonical(dict(schema=SCHEMA, request=request, response=response)); require(len(raw) <= MAX_RESULT_REQUEST, "PROFILE_TOO_LARGE")
            c.execute("INSERT INTO game_command_ledger VALUES (?,?,?,?,?,?,?,?)", (account, key, command, payload, revision, destination, raw.decode("ascii"), sha(raw)))
            self._failpoint("after_ammo_loss_ledger"); self.read_profile(account); self._failpoint("before_ammo_loss_commit")
            c.commit(); return response
        except Exception: c.rollback(); raise

    def results_loss(self, request, *, authenticated_account_id):
        request = validate_results_request(request, authenticated_account_id)
        account, arena = request["account_id"], request["arena_id"]
        require(account == self.pool_account and self.loss_active(), "AMMO_LOSS_POLICY_REQUIRED")
        c = self.connection; c.execute("BEGIN IMMEDIATE" if request["operation"] == "ack" else "BEGIN")
        try:
            aggregate = self.read_profile(account)
            require(self._project_profile(account, aggregate)["native_database_id"] == request["native_database_id"], "FOREIGN_ACCOUNT")
            try: row = self._read_mixed_result(account, request["native_database_id"], arena)
            except TransactionError as error:
                if error.code != "RESULT_NOT_READY": raise
                row = None
            record_contract = None if row is None else "loss-v1" if c.execute("SELECT 1 FROM battle_ammo_loss_reservation WHERE account_id=? AND reservation_id=?", (account, row["reservation_id"])).fetchone() else "mixed-v2"
            value = dict(request, status="missing" if row is None else "found" if request["operation"] == "query" else "acked", acked=bool(row["acked"]) if row else False,
                results_json=row["results_json"] if row else None, replayed=False, code=None, policy_sha256=POLICY_SHA256, record_contract=record_contract)
            require(len(canonical(value)) <= MAX_RESULT_REQUEST, "PROFILE_TOO_LARGE")
            if request["operation"] == "ack":
                payload = sha(canonical(request)); saved = c.execute("SELECT * FROM p06t_command WHERE account_id=? AND command_key=?", (account, request["command_key"])).fetchone()
                if saved is not None:
                    require(saved["payload_sha256"] == payload, "DUPLICATE_PAYLOAD_MISMATCH")
                    old = _json(saved["response_json"])
                    require(sha(canonical(old)) == saved["response_sha256"] and old == dict(value, acked=True), "CORRUPT_STORE")
                    c.commit(); return dict(old, replayed=True)
                if row is not None:
                    c.execute("UPDATE p06t_result SET acked=1 WHERE account_id=? AND arena_id=?", (account, arena)); value["acked"] = True
                    raw = canonical(value); c.execute("INSERT INTO p06t_command VALUES (?,?,?,?,?)", (account, request["command_key"], payload, raw.decode("ascii"), sha(raw)))
                    self._failpoint("before_ammo_loss_ack_commit")
            c.commit(); return value
        except Exception: c.rollback(); raise

    def results_mixed(self,request,*,authenticated_account_id):
        require(not self.loss_active(),"AMMO_LOSS_POLICY_REQUIRED")
        return super().results_mixed(request,authenticated_account_id=authenticated_account_id)


from p06t_mixed_projection import MixedProjectionSource


class AmmoLossProjectionSource(MixedProjectionSource):
    """Actual old source/native bytes plus a distinct policy-bound companion."""
    def __init__(self, source, store):
        require(isinstance(store, AmmoLossStore) and store.loss_active(), "AMMO_LOSS_POLICY_REQUIRED")
        super().__init__(source, store)

    def fixture_files(self, profile, aggregate, layouts):
        files = super().fixture_files(profile, aggregate, layouts)
        files["p06t-ammo-loss.json"] = canonical(dict(version=VERSION, contract=CONTRACT, policy_sha256=POLICY_SHA256,
            base_policy_sha256=BASE_POLICY_SHA256, account_id=profile["account_id"], native_database_id=profile["native_database_id"],
            revision=aggregate["revision"], state_sha256=sha(files["state.bin"])))
        require(len(files["p06t-ammo-loss.json"]) <= 2048, "PROFILE_TOO_LARGE")
        return files


def battle_loss_service(store,request,*,authenticated_account_id):
    request=validate_request(request,authenticated_account_id)
    require(isinstance(store,AmmoLossStore),"AMMO_LOSS_POLICY_REQUIRED")
    try:return store.battle_loss(request,authenticated_account_id=authenticated_account_id)
    except TransactionError as error:
        if error.code not in REJECTIONS:raise
        revision=store.read_profile(authenticated_account_id)["revision"]
        return store._loss_reply(request,revision,"rejected",code=error.code)


def results_loss_service(store,request,*,authenticated_account_id):
    request=validate_results_request(request,authenticated_account_id)
    require(isinstance(store,AmmoLossStore),"AMMO_LOSS_POLICY_REQUIRED")
    try:return store.results_loss(request,authenticated_account_id=authenticated_account_id)
    except TransactionError as error:
        if error.code not in {"RESULT_MISMATCH","DUPLICATE_PAYLOAD_MISMATCH","AMMO_LOSS_POLICY_REQUIRED"}:raise
        return dict(request,status="rejected",acked=False,results_json=None,replayed=False,code=error.code,
            policy_sha256=POLICY_SHA256,record_contract=None)
