"""Versioned conservative presentation append; never a second battle finish.

Candidate only. This module composes the existing single SQLite writer and
source validators. New JSON hashes use sorted compact UTF8; old source hashes
are compared to actual stored receipts without reconstruction or migration.
"""
from copy import deepcopy
import json
import re

from game_profile_tx import TransactionError, _bounded_id
from p09d_ammo_store import require, sha
from p08b_battle_store import _uuid, _integer
from p08c_battle_results import results_value
from p06t_mixed_store import MixedAmmoStore, POLICY_SHA256 as MIXED_POLICY
from p06t_mixed_store import validate_results_request as mixed_results_request
from p06t_ammo_loss_store import AmmoLossStore, POLICY_SHA256 as LOSS_POLICY
from p06t_ammo_loss_store import validate_results_request as loss_results_request
from p09d_ammo_projection import canonical as legacy_canonical

VERSION = 1
CONTRACT = "p08c-late-result-append.v1"
SCHEMA = "p08c-late-results.v1"
POLICY_NAME = "test_lab.p08c.late-result-unchanged-release.v1"
POLICY = dict(id=POLICY_NAME, version=1, mixed_policy_sha256=MIXED_POLICY,
    loss_policy_sha256=LOSS_POLICY, release_reasons=["manual_leave", "disconnect"],
    final_actor="unchanged-hp-crew-device-fire-ammunition-loss-at-release",
    statistics="actual-final-world-accepted-shots-and-interactions",
    inventory="no-finish-no-mutations-no-revision-no-rewards",
    notice="pending-until-durable-native-result1501", unsealed_crash="unavailable")


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf8")


POLICY_SHA256 = sha(canonical(POLICY))
TABLES = {"p08c_late_schema", "p08c_late_seal", "p08c_late_result", "p08c_late_command"}
LINK = {"version", "contract", "operation", "account_id", "native_database_id", "command_key", "run_id",
    "battle_id", "arena_id", "native_inventory_id", "reservation_id", "source_contract", "frozen_sha256"}
STAMP = {"source_contract", "run_id", "battle_id", "arena_id", "reservation_id", "native_inventory_id",
    "frozen_sha256", "release_terminal_sha256", "finished_revision", "reason"}
ACTOR = {"account_id", "native_database_id", "slot", "vehicle_id", "team", "reservation_id",
    "native_inventory_id", "source_contract", "frozen_sha256", "final_actor"}
FINAL = {"terminal_hp", "terminal_state", "remaining_ammunition", "fired_ammunition", "lost_ammunition", "loss_event"}
PENDING = {"version", "contract", "operation", "account_id", "native_database_id", "command_key", "after_arena_id"}
REJECTIONS = {"RELEASE_NOT_READY", "RESULT_MISMATCH", "LATE_ACTOR_STATE_CHANGED", "RUN_FENCED", "FOREIGN_ACCOUNT",
    "DUPLICATE_PAYLOAD_MISMATCH", "UNSUPPORTED_LATE_RESULTS_SCHEMA", "INVALID_INPUT"}


def _hash(value):
    require(type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value), "INVALID_INPUT")


def _unique(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "INVALID_INPUT")
        result[key] = value
    return result


def _tree(value, depth=0, budget=None):
    budget = [4096] if budget is None else budget
    budget[0] -= 1
    require(depth <= 12 and budget[0] >= 0, "INVALID_INPUT")
    if type(value) is dict:
        require(len(value) <= 32, "INVALID_INPUT")
        for key, child in value.items():
            require(type(key) is str and len(key) <= 96, "INVALID_INPUT")
            _tree(child, depth + 1, budget)
    elif type(value) is list:
        require(len(value) <= 64, "INVALID_INPUT")
        for child in value:
            _tree(child, depth + 1, budget)
    elif type(value) is str:
        require(len(value.encode("utf8")) <= 32768, "INVALID_INPUT")
    else:
        require(value is None or type(value) in (int, bool), "INVALID_INPUT")


def decode(raw, maximum=65536):
    require(type(raw) in (str, bytes) and 0 < len(raw.encode("utf8") if type(raw) is str else raw) <= maximum, "INVALID_INPUT")
    try:
        value = json.loads(raw, object_pairs_hook=_unique)
    except (ValueError, UnicodeError, RecursionError):
        raise TransactionError("INVALID_INPUT") from None
    _tree(value)
    return value


def validate_request(value, account):
    require(type(value) is dict and value.get("operation") in ("release_stamp", "append"), "INVALID_INPUT")
    extra = set() if value["operation"] == "release_stamp" else {"release_terminal_sha256", "finished_revision", "seal_json"}
    require(set(value) == LINK | extra and type(value["version"]) is int and value["version"] == VERSION
        and value["contract"] == CONTRACT, "INVALID_INPUT")
    require(value["account_id"] == account, "FOREIGN_ACCOUNT")
    _uuid(account); _uuid(value["run_id"])
    for key in ("native_database_id", "native_inventory_id"):
        _integer(value[key], 1)
    for key in ("command_key", "reservation_id"):
        _bounded_id(value[key], key)
        require(re.fullmatch(r"[A-Za-z0-9_:-]{1,96}", value[key]), "INVALID_INPUT")
    arena = value["arena_id"]
    require(type(arena) is str and re.fullmatch(r"[1-9][0-9]{0,18}", arena) and int(arena) <= 2**63 - 1
        and value["battle_id"] == value["run_id"] + ":" + arena
        and value["source_contract"] in ("mixed-v2", "loss-v1"), "INVALID_INPUT")
    _hash(value["frozen_sha256"])
    if extra:
        _hash(value["release_terminal_sha256"]); _integer(value["finished_revision"], 14)
        require(type(value["seal_json"]) is str and len(value["seal_json"].encode("utf8")) <= 32768, "INVALID_INPUT")
    require(len(canonical(value)) <= (4096 if not extra else 65536), "INVALID_INPUT")
    return deepcopy(value)


def vehicle_id(slot):
    _integer(slot, 0, 5)
    return 0x09100003 + 2 * slot if slot < 2 else 0x09110003 + 2 * (slot - 2)


def validate_pending(value, account):
    require(type(value) is dict and set(value) == PENDING and type(value["version"]) is int and value["version"] == VERSION
        and value["contract"] == CONTRACT and value["operation"] == "pending", "INVALID_INPUT")
    require(value["account_id"] == account, "FOREIGN_ACCOUNT"); _uuid(account); _integer(value["native_database_id"], 1)
    require(type(value["command_key"]) is str and re.fullmatch(r"[A-Za-z0-9_:-]{1,96}", value["command_key"]), "INVALID_INPUT")
    after = value["after_arena_id"]
    require(after is None or type(after) is str and re.fullmatch(r"[1-9][0-9]{0,18}", after) and int(after) <= 2**63-1, "INVALID_INPUT")
    require(len(canonical(value)) <= 2048, "INVALID_INPUT")
    return deepcopy(value)


class LateResults:
    """Small composition helper over the actual selected writer connection."""
    def __init__(self, store):
        require(isinstance(store, MixedAmmoStore), "INVALID_INPUT")
        self.store = store
        self.connection = store.connection
        from p08b_owner_hold_store import require_hold_compatible
        require_hold_compatible(self.connection,store.pool_account,contract=getattr(store,"OWNER_HOLD_CONTRACT",None))

    def namespace(self, create=False):
        c = self.connection
        names = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'p08c_late_%'")}
        require(not names or names == TABLES, "UNSUPPORTED_LATE_RESULTS_SCHEMA")
        if not names and create:
            c.execute("CREATE TABLE p08c_late_schema(version TEXT PRIMARY KEY,policy_sha256 TEXT NOT NULL,catalog_sha256 TEXT NOT NULL)")
            c.execute("INSERT INTO p08c_late_schema VALUES (?,?,?)", (SCHEMA, POLICY_SHA256, self.store.catalog.sha256))
            c.execute("""CREATE TABLE p08c_late_seal(run_id TEXT NOT NULL,battle_id TEXT NOT NULL,arena_id TEXT NOT NULL UNIQUE,
                seal_json TEXT NOT NULL,seal_sha256 TEXT NOT NULL,PRIMARY KEY(run_id,battle_id))""")
            c.execute("""CREATE TABLE p08c_late_result(account_id TEXT NOT NULL,arena_id TEXT NOT NULL,reservation_id TEXT NOT NULL,
                source_contract TEXT NOT NULL,frozen_sha256 TEXT NOT NULL,release_terminal_sha256 TEXT NOT NULL,
                finished_revision INTEGER NOT NULL,seal_sha256 TEXT NOT NULL,acked INTEGER NOT NULL CHECK(acked IN (0,1)),
                PRIMARY KEY(account_id,arena_id),UNIQUE(account_id,reservation_id),
                FOREIGN KEY(account_id,reservation_id) REFERENCES p06t_reservation(account_id,reservation_id))""")
            c.execute("""CREATE TABLE p08c_late_command(account_id TEXT NOT NULL,command_key TEXT NOT NULL,payload_sha256 TEXT NOT NULL,
                response_json TEXT NOT NULL,response_sha256 TEXT NOT NULL,PRIMARY KEY(account_id,command_key))""")
            c.execute("CREATE INDEX p08c_late_pending_idx ON p08c_late_result(account_id,acked,arena_id)")
            names = TABLES
        if names:
            require([tuple(r) for r in c.execute("SELECT * FROM p08c_late_schema")] == [(SCHEMA, POLICY_SHA256, self.store.catalog.sha256)], "UNSUPPORTED_LATE_RESULTS_SCHEMA")
        return bool(names)

    def native(self, account, native):
        from p08b_owner_hold_store import require_hold_compatible
        require_hold_compatible(self.connection,account,contract=getattr(self.store,"OWNER_HOLD_CONTRACT",None))
        row = self.connection.execute("SELECT profile_json FROM game_profiles WHERE account_id=?", (account,)).fetchone()
        require(row is not None, "FOREIGN_ACCOUNT")
        profile = decode(row[0], 131072)
        require(profile["account_id"] == account and profile["native_database_id"] == native and profile["profile_version"] == 13, "FOREIGN_ACCOUNT")

    def source(self, link):
        from p08b_owner_hold_store import namespace
        if namespace(self.connection):
            require(self.connection.execute("SELECT 1 FROM battle_owner_hold_reservation WHERE account_id=? AND reservation_id=?",(link["account_id"],link["reservation_id"])).fetchone()is None,"OWNER_HOLD_POLICY_REQUIRED")
        _uuid(link["account_id"])
        _integer(link["native_database_id"], 1); _integer(link["native_inventory_id"], 1)
        require(link["source_contract"] in ("mixed-v2", "loss-v1"), "RESULT_MISMATCH")
        _hash(link["frozen_sha256"])
        require(type(link["reservation_id"]) is str and re.fullmatch(r"[A-Za-z0-9_:-]{1,96}", link["reservation_id"]), "RESULT_MISMATCH")
        self.native(link["account_id"], link["native_database_id"])
        row = self.connection.execute("SELECT * FROM p06t_reservation WHERE account_id=? AND reservation_id=?", (link["account_id"], link["reservation_id"])).fetchone()
        require(row is not None, "RELEASE_NOT_READY")
        # A peer may legitimately restart/refund after this owner's immutable
        # final seal was committed. Original readers validate that abort plus
        # its unchanged admitted Frozen; it is never an eligible owner release.
        require(row["status"] in ("active", "finished", "aborted_restart"), "RELEASE_NOT_READY")
        loss = self.connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='battle_ammo_loss_reservation'").fetchone()
        side = self.connection.execute("SELECT * FROM battle_ammo_loss_reservation WHERE account_id=? AND reservation_id=?", (link["account_id"], link["reservation_id"])).fetchone() if loss else None
        require((side is not None) == (link["source_contract"] == "loss-v1"), "RESULT_MISMATCH")
        if side is None:
            value = MixedAmmoStore._mixed_reservation(self.store, row)
            frozen, frozen_sha, terminal, terminal_sha = value["frozen"], value["frozen_sha256"], value["result"], row["result_sha256"]
        else:
            require(isinstance(self.store, AmmoLossStore), "RESULT_MISMATCH")
            value = self.store._loss_reservation(row)
            frozen, frozen_sha, terminal, terminal_sha = value["frozen"]["loadout"], value["frozen_sha256"], value["result"], side["result_sha256"]
        require(row["run_id"] == link["run_id"] and row["battle_id"] == link["battle_id"]
            and row["native_inventory_id"] == link["native_inventory_id"] and frozen_sha == link["frozen_sha256"], "RESULT_MISMATCH")
        return row, frozen, terminal, terminal_sha

    def stamp(self, request):
        row, frozen, terminal, terminal_sha = self.source(request)
        require(row["status"] == "finished" and terminal is not None, "RELEASE_NOT_READY")
        require(terminal["reason"] in ("manual_leave", "disconnect", "battle_finished"), "RELEASE_NOT_READY")
        return {key: request[key] for key in STAMP - {"release_terminal_sha256", "finished_revision", "reason"}} | dict(
            release_terminal_sha256=terminal_sha, finished_revision=row["finished_revision"], reason=terminal["reason"])

    @staticmethod
    def reply(request, status, stamp=None, seal_sha=None, replayed=False, code=None):
        value = {key: request[key] for key in ("version", "contract", "operation", "account_id", "native_database_id", "command_key")}
        value.update(request_sha256=sha(canonical(request)), policy_sha256=POLICY_SHA256, status=status,
            replayed=replayed, code=code, seal_sha256=seal_sha, release_stamp=stamp)
        require(len(canonical(value)) <= 4096, "INVALID_INPUT")
        return value

    def release_stamp(self, request, authenticated_account_id):
        from p08b_owner_hold_store import require_hold_compatible
        require_hold_compatible(self.connection,authenticated_account_id)
        request = validate_request(request, authenticated_account_id)
        require(request["operation"] == "release_stamp" and authenticated_account_id == self.store.pool_account, "FOREIGN_ACCOUNT")
        c = self.connection
        require(not c.in_transaction, "LATE_TRANSACTION_REQUIRED")
        prior = c.execute("PRAGMA query_only").fetchone()[0]
        c.execute("PRAGMA query_only=ON"); c.execute("BEGIN")
        try:
            require_hold_compatible(self.connection,authenticated_account_id)
            self.namespace(); result = self.reply(request, "stamped", self.stamp(request)); c.commit(); return result
        except Exception:
            c.rollback(); raise
        finally:
            c.execute("PRAGMA query_only=" + str(prior))

    def validate_seal(self, request):
        raw = request["seal_json"]; seal = decode(raw, 32768)
        require(type(seal) is dict and set(seal) == {"version", "policy", "run_id", "battle_id", "arena_id", "results_json", "actors"}
            and type(seal["version"]) is int and seal["version"] == 1 and seal["policy"] == POLICY_NAME
            and all(seal[k] == request[k] for k in ("run_id", "battle_id", "arena_id")) and canonical(seal).decode("utf8") == raw, "RESULT_MISMATCH")
        results = results_value(seal["results_json"])
        require(canonical(results).decode("utf8") == seal["results_json"] and results["arena_id"] == int(request["arena_id"]), "RESULT_MISMATCH")
        actors = seal["actors"]
        require(type(actors) is list and len(actors) == len(results["participants"]) and 2 <= len(actors) <= 6, "RESULT_MISMATCH")
        owners = set(); selected = None
        for slot, (actor, participant) in enumerate(zip(actors, results["participants"])):
            require(type(actor) is dict and set(actor) == ACTOR and actor["slot"] == slot
                and type(actor["slot"]) is int and actor["vehicle_id"] == participant["vehicle_id"] == vehicle_id(slot)
                and type(actor["vehicle_id"]) is int and type(actor["team"]) is int
                and actor["native_database_id"] == participant["account_dbid"] and actor["team"] == participant["team"]
                and actor["account_id"] not in owners, "RESULT_MISMATCH")
            _uuid(actor["account_id"]); owners.add(actor["account_id"])
            link = dict(actor, run_id=seal["run_id"], battle_id=seal["battle_id"])
            row, frozen, released, released_sha = self.source(link)
            require(released is None or released["reason"] in ("manual_leave", "disconnect", "battle_finished")
                or actor["account_id"] != request["account_id"] and row["status"] == "aborted_restart"
                    and released["reason"] == "aborted_restart", "RESULT_MISMATCH")
            final = actor["final_actor"]
            require(type(final) is dict and set(final) == FINAL, "RESULT_MISMATCH")
            computed = self.store._accounting(frozen, final["remaining_ammunition"], final["fired_ammunition"], final["lost_ammunition"],
                final["loss_event"], final["terminal_hp"], "battle_finished", final["terminal_state"]) if actor["source_contract"] == "loss-v1" else self.store._terminal(
                    frozen, final["remaining_ammunition"], final["terminal_hp"], "battle_finished", terminal_state=final["terminal_state"])
            if actor["source_contract"] == "mixed-v2":
                require(final["fired_ammunition"] == computed["consumed_ammunition"] and final["loss_event"] is None
                    and final["lost_ammunition"] == [dict(r, count=0) for r in computed["consumed_ammunition"]], "RESULT_MISMATCH")
            state = self.store.terminal_policy.validate(canonical(final["terminal_state"]).decode("utf8"), frozen=frozen, terminal_hp=final["terminal_hp"], results=results)
            require(participant["type_compact_descr"] == self.store.registry.profiles[frozen["kind"]].type_compact_id
                and participant["health"] == final["terminal_hp"] and participant["shots"] == sum(r["count"] for r in final["fired_ammunition"])
                and participant["death_reason"] == state["death"]["reason"]
                and participant["killer_id"] == (0 if state["death"]["killer_slot"] is None else results["participants"][state["death"]["killer_slot"]]["vehicle_id"]), "RESULT_MISMATCH")
            if actor["account_id"] == request["account_id"]:
                require(all(actor[k] == request[k] for k in ("native_database_id", "native_inventory_id", "reservation_id", "source_contract", "frozen_sha256")), "RESULT_MISMATCH")
                selected = (row, computed, released)
        require(selected is not None, "RESULT_MISMATCH")
        row, computed, released = selected
        require(released is not None and released["reason"] in ("manual_leave", "disconnect", "battle_finished"), "RELEASE_NOT_READY")
        require(all(computed[k] == v for k, v in released.items() if k != "reason"), "LATE_ACTOR_STATE_CHANGED")
        return seal, results, row

    def cache_rows(self, account, arena):
        found = []
        for table in ("p08c_result", "p06t_result", "p08c_late_result"):
            if self.connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone():
                row = self.connection.execute("SELECT * FROM " + table + " WHERE account_id=? AND arena_id=?", (account, arena)).fetchone()
                if row is not None: found.append((table, row))
        require(len(found) <= 1, "RESULT_MISMATCH")
        return found

    def append(self, request, authenticated_account_id):
        from p08b_owner_hold_store import require_hold_compatible
        require_hold_compatible(self.connection,authenticated_account_id)
        request = validate_request(request, authenticated_account_id)
        require(request["operation"] == "append" and authenticated_account_id == self.store.pool_account, "FOREIGN_ACCOUNT")
        c = self.connection; require(not c.in_transaction, "LATE_TRANSACTION_REQUIRED"); c.execute("BEGIN IMMEDIATE")
        try:
            require_hold_compatible(self.connection,authenticated_account_id)
            stamp = self.stamp(request)
            require(all(stamp[k] == request[k] for k in ("release_terminal_sha256", "finished_revision")), "RESULT_MISMATCH")
            seal, results, source = self.validate_seal(request); seal_sha = sha(canonical(seal)); self.namespace(create=True)
            saved = c.execute("SELECT * FROM p08c_late_command WHERE account_id=? AND command_key=?", (authenticated_account_id, request["command_key"])).fetchone()
            if saved is not None:
                require(saved["payload_sha256"] == sha(canonical(request)), "DUPLICATE_PAYLOAD_MISMATCH")
                value = decode(saved["response_json"], 4096)
                require(sha(canonical(value)) == saved["response_sha256"] and value == self.reply(request, value["status"], stamp, seal_sha), "RESULT_MISMATCH")
                c.commit(); return dict(value, replayed=True)
            common = c.execute("SELECT * FROM p08c_late_seal WHERE arena_id=?", (request["arena_id"],)).fetchone()
            if common is None:
                require(self.store._current_run(authenticated_account_id) == request["run_id"], "RUN_FENCED")
                c.execute("INSERT INTO p08c_late_seal VALUES (?,?,?,?,?)", (request["run_id"], request["battle_id"], request["arena_id"], request["seal_json"], seal_sha))
            else:
                require(common["run_id"] == request["run_id"] and common["battle_id"] == request["battle_id"]
                    and common["seal_json"] == request["seal_json"] and common["seal_sha256"] == seal_sha, "RESULT_MISMATCH")
            self.store._failpoint("after_late_seal")
            existing = self.cache_rows(authenticated_account_id, request["arena_id"])
            status = "already_present" if existing else "appended"
            if existing:
                table, old = existing[0]
                require(old["reservation_id"] == request["reservation_id"], "RESULT_MISMATCH")
                if table == "p06t_result":
                    require(stamp["reason"] == "battle_finished" and results_value(old["results_json"]) == results, "RESULT_MISMATCH")
                    self.store._read_mixed_result(authenticated_account_id, request["native_database_id"], request["arena_id"])
                else:
                    require(table == "p08c_late_result" and old["seal_sha256"] == seal_sha and all(old[k] == request[k] for k in ("source_contract", "frozen_sha256", "release_terminal_sha256", "finished_revision")), "RESULT_MISMATCH")
            else:
                require(stamp["reason"] in ("manual_leave", "disconnect"), "RESULT_MISMATCH")
                c.execute("INSERT INTO p08c_late_result VALUES (?,?,?,?,?,?,?,?,0)", (authenticated_account_id, request["arena_id"], request["reservation_id"],
                    request["source_contract"], request["frozen_sha256"], request["release_terminal_sha256"], request["finished_revision"], seal_sha))
            self.store._failpoint("after_late_result_notice")
            reply = self.reply(request, status, stamp, seal_sha); raw = canonical(reply)
            c.execute("INSERT INTO p08c_late_command VALUES (?,?,?,?,?)", (authenticated_account_id, request["command_key"], sha(canonical(request)), raw.decode("utf8"), sha(raw)))
            self.store._failpoint("before_late_append_commit"); c.commit(); return reply
        except Exception:
            c.rollback(); raise

    def read_late(self, account, native, arena):
        self.native(account, native); self.namespace()
        rows = self.cache_rows(account, arena)
        if not rows or rows[0][0] != "p08c_late_result": return None
        row = rows[0][1]
        common = self.connection.execute("SELECT * FROM p08c_late_seal WHERE arena_id=?", (arena,)).fetchone()
        require(common is not None and sha(common["seal_json"].encode("utf8")) == common["seal_sha256"] == row["seal_sha256"], "RESULT_MISMATCH")
        seal = decode(common["seal_json"], 32768)
        source_row = self.connection.execute("SELECT * FROM p06t_reservation WHERE account_id=? AND reservation_id=?", (account, row["reservation_id"])).fetchone()
        require(source_row is not None, "RESULT_MISMATCH")
        request = dict(version=VERSION, contract=CONTRACT, operation="append", account_id=account, native_database_id=native,
            command_key="late:read", run_id=common["run_id"], battle_id=common["battle_id"], arena_id=arena,
            native_inventory_id=source_row["native_inventory_id"], reservation_id=row["reservation_id"], source_contract=row["source_contract"],
            frozen_sha256=row["frozen_sha256"], release_terminal_sha256=row["release_terminal_sha256"],
            finished_revision=row["finished_revision"], seal_json=common["seal_json"])
        stamp = self.stamp(request)
        require(stamp["release_terminal_sha256"] == row["release_terminal_sha256"] and stamp["finished_revision"] == row["finished_revision"], "RESULT_MISMATCH")
        self.validate_seal(request)
        return dict(row) | dict(results_json=seal["results_json"])

    def results(self, request, authenticated_account_id):
        require(not self.connection.in_transaction, "LATE_TRANSACTION_REQUIRED")
        loss = isinstance(self.store, AmmoLossStore) and self.store.loss_active()
        request = (loss_results_request if loss else mixed_results_request)(request, authenticated_account_id)
        require(authenticated_account_id == self.store.pool_account, "FOREIGN_ACCOUNT")
        c = self.connection; c.execute("BEGIN IMMEDIATE" if request["operation"] == "ack" else "BEGIN")
        try:
            aggregate = self.store.read_profile(authenticated_account_id)
            require(self.store._project_profile(authenticated_account_id, aggregate)["native_database_id"] == request["native_database_id"], "FOREIGN_ACCOUNT")
            namespace = self.namespace()
            saved = c.execute("SELECT * FROM p08c_late_command WHERE account_id=? AND command_key=?", (authenticated_account_id, request["command_key"])).fetchone() if namespace and request["operation"] == "ack" else None
            if saved is not None:
                require(saved["payload_sha256"] == sha(canonical(request)), "DUPLICATE_PAYLOAD_MISMATCH")
            exists = c.execute("SELECT 1 FROM p08c_late_result WHERE account_id=? AND arena_id=?", (authenticated_account_id, request["arena_id"])).fetchone() if namespace else None
            if exists is None:
                require(saved is None, "RESULT_MISMATCH")
                value = self.archived_results(request, loss)
                c.commit(); return value
            row = self.read_late(authenticated_account_id, request["native_database_id"], request["arena_id"])
            require(row is not None, "RESULT_MISMATCH")
            reply = dict(request, status="found" if request["operation"] == "query" else "acked", acked=bool(row["acked"]),
                results_json=row["results_json"], replayed=False, code=None, policy_sha256=LOSS_POLICY if loss else MIXED_POLICY)
            if loss: reply["record_contract"] = row["source_contract"]
            if request["operation"] == "ack":
                key = request["command_key"]; payload = sha(canonical(request))
                require(c.execute("SELECT 1 FROM p06t_command WHERE account_id=? AND command_key=?", (authenticated_account_id, key)).fetchone() is None, "DUPLICATE_PAYLOAD_MISMATCH")
                old = saved
                if old is not None:
                    require(old["payload_sha256"] == payload, "DUPLICATE_PAYLOAD_MISMATCH")
                    previous = decode(old["response_json"], 65536)
                    require(sha(canonical(previous)) == old["response_sha256"] and previous == dict(reply, acked=True), "RESULT_MISMATCH")
                    c.commit(); return dict(previous, replayed=True)
                c.execute("UPDATE p08c_late_result SET acked=1 WHERE account_id=? AND arena_id=?", (authenticated_account_id, request["arena_id"]))
                reply["acked"] = True; raw = canonical(reply)
                c.execute("INSERT INTO p08c_late_command VALUES (?,?,?,?,?)", (authenticated_account_id, key, payload, raw.decode("utf8"), sha(raw)))
                self.store._failpoint("before_late_ack_commit")
            require(len(canonical(reply)) <= 65536, "INVALID_INPUT"); c.commit(); return reply
        except Exception:
            c.rollback(); raise

    def archived_results(self, request, loss):
        """Original archive validator/receipt recipe inside this same owned TX.

        Do not call the old public method after dropping the lock: another late
        acknowledgement could otherwise claim the same command key in that gap.
        """
        account, arena = request["account_id"], request["arena_id"]; c = self.connection
        try: row = self.store._read_mixed_result(account, request["native_database_id"], arena)
        except TransactionError as error:
            if error.code != "RESULT_NOT_READY": raise
            row = None
        status = "missing" if row is None else "found" if request["operation"] == "query" else "acked"
        if loss:
            record = None if row is None else "loss-v1" if c.execute("SELECT 1 FROM battle_ammo_loss_reservation WHERE account_id=? AND reservation_id=?", (account, row["reservation_id"])).fetchone() else "mixed-v2"
            value = dict(request, status=status, acked=bool(row["acked"]) if row else False, results_json=row["results_json"] if row else None,
                replayed=False, code=None, policy_sha256=LOSS_POLICY, record_contract=record)
        else: value = self.store._mixed_results_reply(request, status, row)
        if request["operation"] == "ack":
            payload = sha(legacy_canonical(request))
            saved = c.execute("SELECT * FROM p06t_command WHERE account_id=? AND command_key=?", (account, request["command_key"])).fetchone()
            if saved is not None:
                require(saved["payload_sha256"] == payload, "DUPLICATE_PAYLOAD_MISMATCH")
                previous = decode(saved["response_json"], 65536)
                require(sha(legacy_canonical(previous)) == saved["response_sha256"] and previous == dict(value, acked=True), "RESULT_MISMATCH")
                return dict(previous, replayed=True)
            if row is not None:
                c.execute("UPDATE p06t_result SET acked=1 WHERE account_id=? AND arena_id=?", (account, arena)); value["acked"] = True
                raw = legacy_canonical(value)
                c.execute("INSERT INTO p06t_command VALUES (?,?,?,?,?)", (account, request["command_key"], payload, raw.decode("ascii"), sha(raw)))
                self.store._failpoint("before_ammo_loss_ack_commit" if loss else "before_mixed_ack_commit")
        require(len(legacy_canonical(value)) <= 65536, "INVALID_INPUT")
        return value

    def pending_page(self, account, native, after=None, limit=8):
        _integer(limit, 1, 8); _integer(native, 1); require(account == self.store.pool_account, "FOREIGN_ACCOUNT")
        require(after is None or type(after) is str and re.fullmatch(r"[1-9][0-9]{0,18}", after) and int(after) <= 2**63-1, "INVALID_INPUT")
        c = self.connection; require(not c.in_transaction, "LATE_TRANSACTION_REQUIRED")
        previous = c.execute("PRAGMA query_only").fetchone()[0]
        c.execute("PRAGMA query_only=ON"); c.execute("BEGIN")
        try:
            aggregate = self.store.read_profile(account)
            require(self.store._project_profile(account, aggregate)["native_database_id"] == native, "FOREIGN_ACCOUNT")
            self.native(account, native); values = []; more = False
            if self.namespace():
                sql = "SELECT arena_id FROM p08c_late_result WHERE account_id=? AND acked=0"
                params = [account]
                if after is not None: sql += " AND arena_id>?"; params.append(after)
                rows = c.execute(sql + " ORDER BY arena_id LIMIT ?", (*params, limit + 1)).fetchall(); more = len(rows) > limit
                for row in rows[:limit]:
                    actual = self.read_late(account, native, row[0]); result = results_value(actual["results_json"])
                    own = next(p for p in result["participants"] if p["account_dbid"] == native)
                    values.append(dict(arena_id=row[0], seal_sha256=actual["seal_sha256"], arena_type_id=result["arena_type_id"],
                        created_unix=result["created_unix"], winner_team=result["winner_team"], own_team=own["team"],
                        vehicle_type_compact_id=own["type_compact_descr"]))
            c.commit(); return values, values[-1]["arena_id"] if more else None
        except Exception:
            c.rollback(); raise
        finally:
            c.execute("PRAGMA query_only=" + str(previous))

    def pending(self, account, native, limit=8):
        return self.pending_page(account, native, limit=limit)[0]


class _LateMixin:
    def _arena_has_result(self, account, arena):
        adapter = LateResults(self)
        if adapter.namespace() and self.connection.execute("SELECT 1 FROM p08c_late_result WHERE account_id=? AND arena_id=?", (account, arena)).fetchone(): return True
        return super()._arena_has_result(account, arena)

class LateResultsStore(_LateMixin, MixedAmmoStore):
    def results_mixed(self, request, *, authenticated_account_id):
        self._ammo_loss_fence()
        require(self.mixed_active(), "FOREIGN_ACCOUNT")
        return LateResults(self).results(request, authenticated_account_id)


class LossLateResultsStore(_LateMixin, AmmoLossStore):
    def results_loss(self, request, *, authenticated_account_id):
        require(self.loss_active(), "AMMO_LOSS_POLICY_REQUIRED")
        return LateResults(self).results(request, authenticated_account_id)


def service(store, request, *, authenticated_account_id):
    request = validate_request(request, authenticated_account_id)
    require(isinstance(store, (LateResultsStore, LossLateResultsStore)), "INVALID_INPUT")
    adapter = LateResults(store)
    try:
        if request["operation"] == "release_stamp": return adapter.release_stamp(request, authenticated_account_id)
        return adapter.append(request, authenticated_account_id)
    except TransactionError as error:
        if error.code not in REJECTIONS: raise
        return adapter.reply(request, "rejected", code=error.code)


def pending_service(store, request, *, authenticated_account_id):
    request = validate_pending(request, authenticated_account_id)
    require(isinstance(store, (LateResultsStore, LossLateResultsStore)), "INVALID_INPUT")
    value = dict(request, request_sha256=sha(canonical(request)), policy_sha256=POLICY_SHA256,
        status="pending", replayed=False, code=None, rows=[], next_arena_id=None)
    try:
        value["rows"], value["next_arena_id"] = LateResults(store).pending_page(authenticated_account_id, request["native_database_id"], request["after_arena_id"])
    except TransactionError as error:
        if error.code not in REJECTIONS: raise
        value.update(status="rejected", code=error.code)
    require(len(canonical(value)) <= 4096, "INVALID_INPUT")
    return value
