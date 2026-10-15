"""Bounded owner result journal beside the existing authoritative battle writer.

No client pickle or client statistics enter this API. Only the configured
gateway supplies primitive Results JSON after its own durable terminal finish.
"""
from __future__ import annotations

from copy import deepcopy
import json
import re
import unicodedata

from game_profile_tx import TransactionError, _bounded_id
from p08b_battle_store import BattleStore, POLICY_SHA256, _integer, _uuid, validate_request as battle_request
from p09d_ammo_store import require, sha
from p09d_ammo_projection import canonical

SCHEMA = "p08c-battle-results.v1"
MAX_RESULT_BYTES = 32768
MAX_HTTP_BYTES = 65536
COMMON = {"version", "operation", "account_id", "native_database_id", "command_key", "arena_id"}
STORE = {"run_id", "battle_id", "native_inventory_id", "reservation_id", "results_json"}
HEADER = {"arena_id", "arena_type_id", "created_unix", "winner_team", "finish_reason", "duration_seconds", "participants"}
PARTICIPANT = {"vehicle_id", "account_dbid", "name", "team", "type_compact_descr", "health", "shots", "direct_hits",
    "piercings", "damage_dealt", "damage_received", "kills", "capture_points", "dropped_capture_points", "mileage_metres",
    "life_time", "killer_id", "death_reason", "premature_leave"}
REJECTIONS = frozenset(("RESULT_NOT_READY", "RESULT_MISMATCH", "DUPLICATE_PAYLOAD_MISMATCH"))


def _unique(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "INVALID_INPUT")
        result[key] = value
    return result


def results_value(raw):
    require(type(raw) is str and len(raw.encode("utf-8")) <= MAX_RESULT_BYTES, "INVALID_INPUT")
    try:
        value = json.loads(raw, object_pairs_hook=_unique,
            parse_float=lambda _: (_ for _ in ()).throw(TransactionError("INVALID_INPUT")),
            parse_constant=lambda _: (_ for _ in ()).throw(TransactionError("INVALID_INPUT")))
    except (ValueError, RecursionError, UnicodeError) as error:
        raise TransactionError("INVALID_INPUT") from error
    require(type(value) is dict and set(value) == HEADER, "INVALID_INPUT")
    _integer(value["arena_id"], 1, 2**63 - 1)
    require(type(value["arena_type_id"]) is int and value["arena_type_id"] in (1, 4), "INVALID_INPUT")
    _integer(value["created_unix"], 1, 2**32 - 1); _integer(value["winner_team"], 0, 2)
    _integer(value["finish_reason"], 1, 5); _integer(value["duration_seconds"], 0, 3600)
    rows = value["participants"]
    require(type(rows) is list and 2 <= len(rows) <= 6, "INVALID_INPUT")
    ids, owners, teams = set(), set(), set()
    for row in rows:
        require(type(row) is dict and set(row) == PARTICIPANT, "INVALID_INPUT")
        for field in ("vehicle_id", "account_dbid", "type_compact_descr"): _integer(row[field], 1)
        _integer(row["team"], 1, 2); _integer(row["health"], 0, 10000)
        for field in ("shots", "direct_hits", "piercings"): _integer(row[field], 0, 192)
        for field, maximum in (("damage_dealt", 60000), ("damage_received", 10000), ("kills", 6),
            ("capture_points", 600), ("dropped_capture_points", 600), ("mileage_metres", 200000),
            ("life_time", value["duration_seconds"]), ("killer_id", 2**31 - 1)):
            _integer(row[field], 0, maximum)
        _integer(row["death_reason"], -1, 10)
        require(type(row["premature_leave"]) is bool and type(row["name"]) is str
            and 1 <= len(row["name"].encode("utf-8")) <= 48
            and not any(unicodedata.category(c) == "Cc" for c in row["name"]), "INVALID_INPUT")
        require(row["vehicle_id"] not in ids and row["account_dbid"] not in owners, "INVALID_INPUT")
        ids.add(row["vehicle_id"]); owners.add(row["account_dbid"]); teams.add(row["team"])
    require(teams == {1, 2}, "INVALID_INPUT")
    require(len(canonical(value)) <= MAX_RESULT_BYTES, "INVALID_INPUT")
    return value


def validate_request(value, authenticated_account_id):
    require(type(value) is dict and type(value.get("operation")) is str
        and value["operation"] in ("store", "query", "ack"), "INVALID_INPUT")
    require(set(value) == COMMON | (STORE if value["operation"] == "store" else set()), "INVALID_INPUT")
    require(type(value["version"]) is int and value["version"] == 1, "INVALID_INPUT")
    require(value["account_id"] == authenticated_account_id, "FOREIGN_ACCOUNT")
    _uuid(authenticated_account_id); _integer(value["native_database_id"], 1)
    _bounded_id(value["command_key"], "command_key")
    require(re.fullmatch(r"[A-Za-z0-9_:-]{1,96}", value["command_key"]) is not None, "INVALID_INPUT")
    arena = value["arena_id"]
    require(type(arena) is str and re.fullmatch(r"[1-9][0-9]{0,18}", arena) is not None
        and int(arena) <= 2**63 - 1, "INVALID_INPUT")
    if value["operation"] == "store":
        _uuid(value["run_id"]); _integer(value["native_inventory_id"], 1)
        _bounded_id(value["reservation_id"], "reservation_id")
        require(value["battle_id"] == value["run_id"] + ":" + arena, "INVALID_INPUT")
        result = results_value(value["results_json"])
        require(result["arena_id"] == int(arena) and any(p["account_dbid"] == value["native_database_id"]
            for p in result["participants"]), "RESULT_MISMATCH")
        value = dict(value, results_json=canonical(result).decode("ascii"))
    require(len(canonical(value)) <= MAX_HTTP_BYTES, "INVALID_INPUT")
    return deepcopy(value)


class ResultsStore(BattleStore):
    """Additive tables; profile/vehicle/ammo revisions never change on receipt."""
    def battle(self, request, *, authenticated_account_id):
        request = battle_request(request, authenticated_account_id)
        if request.get("reason") == "battle_finished":
            # Hash semantic closed DTOs, not irrelevant whitespace/key order.
            # Six bounded participants also keep the existing <=32KiB ledger
            # reader valid even when the trusted sender used padded JSON.
            request["results_json"] = canonical(results_value(request["results_json"])).decode("ascii")
        return super().battle(request, authenticated_account_id=authenticated_account_id)

    def _record_natural_result(self, request, reservation):
        # Called by BattleStore._finish BEFORE its existing atomic projection,
        # command ledger and COMMIT. A crash cannot separate finish and stats.
        value = results_value(request["results_json"])
        arena = str(value["arena_id"])
        require(request["battle_id"] == request["run_id"] + ":" + arena, "RESULT_MISMATCH")
        self._match_result(value, reservation, request["native_database_id"], arena)
        self._results_schema(); raw = canonical(value).decode("ascii")
        self.connection.execute("INSERT INTO p08c_result VALUES (?,?,?,?,?,0)",
            (request["account_id"], arena, request["reservation_id"], raw, sha(raw.encode("ascii"))))
        self._failpoint("after_results_insert")

    def _verify_natural_result(self, request, reservation):
        self._results_schema()
        arena = request["battle_id"].rsplit(":", 1)[1]
        row = self._read_result(request["account_id"], request["native_database_id"], arena)
        require(row is not None and row["reservation_id"] == reservation["reservation_id"]
            and row["results_json"] == canonical(results_value(request["results_json"])).decode("ascii"), "CORRUPT_STORE")

    def _results_schema(self):
        c = self.connection
        tables = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name IN ('p08c_schema','p08c_result','p08c_command')")}
        require(not tables or tables == {"p08c_schema", "p08c_result", "p08c_command"}, "UNSUPPORTED_RESULTS_SCHEMA")
        c.execute("""CREATE TABLE IF NOT EXISTS p08c_schema(version TEXT PRIMARY KEY,
            battle_policy_sha256 TEXT NOT NULL,catalog_sha256 TEXT NOT NULL)""")
        rows = c.execute("SELECT * FROM p08c_schema").fetchall()
        if not tables:
            c.execute("INSERT INTO p08c_schema VALUES (?,?,?)", (SCHEMA, POLICY_SHA256, self.catalog.sha256))
        else: require([tuple(r) for r in rows] == [(SCHEMA, POLICY_SHA256, self.catalog.sha256)], "UNSUPPORTED_RESULTS_SCHEMA")
        c.execute("""CREATE TABLE IF NOT EXISTS p08c_result(account_id TEXT NOT NULL,arena_id TEXT NOT NULL,
            reservation_id TEXT NOT NULL,results_json TEXT NOT NULL,results_sha256 TEXT NOT NULL,
            acked INTEGER NOT NULL CHECK(acked IN (0,1)),PRIMARY KEY(account_id,arena_id),
            UNIQUE(account_id,reservation_id),FOREIGN KEY(account_id,reservation_id)
            REFERENCES p08b_reservation(account_id,reservation_id))""")
        c.execute("""CREATE TABLE IF NOT EXISTS p08c_command(account_id TEXT NOT NULL,command_key TEXT NOT NULL,
            operation TEXT NOT NULL,payload_sha256 TEXT NOT NULL,response_json TEXT NOT NULL,response_sha256 TEXT NOT NULL,
            PRIMARY KEY(account_id,command_key),FOREIGN KEY(account_id) REFERENCES game_snapshot(account_id))""")
        self._failpoint("after_results_schema")

    def _bound_reservation(self, account, native_id, arena, row):
        require(row is not None, "RESULT_NOT_READY")
        reservation = self._reservation(row)
        require(reservation["status"] == "finished" and reservation["result"]["reason"] == "battle_finished", "RESULT_NOT_READY")
        require(row["battle_id"] == row["run_id"] + ":" + arena, "RESULT_MISMATCH")
        return reservation

    def _read_result(self, account, native_id, arena):
        row = self.connection.execute("SELECT * FROM p08c_result WHERE account_id=? AND arena_id=?", (account, arena)).fetchone()
        if row is None: return None
        require(len(row["results_json"].encode("utf-8")) <= MAX_RESULT_BYTES
            and sha(row["results_json"].encode("ascii")) == row["results_sha256"], "CORRUPT_STORE")
        value = results_value(row["results_json"])
        reservation_row = self.connection.execute("SELECT * FROM p08b_reservation WHERE account_id=? AND reservation_id=?",
            (account, row["reservation_id"])).fetchone()
        reservation = self._bound_reservation(account, native_id, arena, reservation_row)
        self._match_result(value, reservation, native_id, arena)
        return row

    @staticmethod
    def _match_result(value, reservation, native_id, arena):
        own = next((p for p in value["participants"] if p["account_dbid"] == native_id), None)
        frozen, terminal = reservation["frozen"], reservation["result"]
        require(value["arena_id"] == int(arena) and own is not None
            and own["type_compact_descr"] == (3329 if frozen["kind"] == "ms1" else 7169)
            and own["health"] == terminal["terminal_hp"] <= frozen["max_hp"]
            and own["shots"] == terminal["consumed_ap"] == frozen["ap_count"] - terminal["remaining_ap"], "RESULT_MISMATCH")

    @staticmethod
    def _results_reply(request, status, row=None, *, code=None, replayed=False):
        value = {key: request[key] for key in ("version", "operation", "account_id", "native_database_id", "command_key", "arena_id")}
        value.update(status=status, acked=bool(row["acked"]) if row else False, replayed=replayed,
            results_json=row["results_json"] if row else None, code=code)
        require(len(canonical(value)) <= MAX_HTTP_BYTES, "PROFILE_TOO_LARGE")
        return value

    def results(self, request, *, authenticated_account_id):
        request = validate_request(request, authenticated_account_id)
        self.initialize(); c = self.connection; c.execute("BEGIN IMMEDIATE")
        try:
            self._results_schema(); account, native_id = request["account_id"], request["native_database_id"]
            aggregate = self.read_profile(account)
            require(self._project_profile(account, aggregate)["native_database_id"] == native_id, "FOREIGN_ACCOUNT")
            key, operation, arena = request["command_key"], request["operation"], request["arena_id"]
            payload_sha = sha(canonical(request))
            ledger = c.execute("SELECT * FROM p08c_command WHERE account_id=? AND command_key=?", (account, key)).fetchone()
            if ledger is not None:
                require(ledger["operation"] == operation and ledger["payload_sha256"] == payload_sha, "DUPLICATE_PAYLOAD_MISMATCH")
                require(sha(ledger["response_json"].encode("ascii")) == ledger["response_sha256"], "CORRUPT_STORE")
                response = json.loads(ledger["response_json"], object_pairs_hook=_unique)
                require(response == self._results_reply(request, response["status"],
                    {"results_json": response["results_json"], "acked": response["acked"]}), "CORRUPT_STORE")
                current = self._read_result(account, native_id, arena)
                require(current is not None and current["results_json"] == response["results_json"]
                    and response["status"] == ("stored" if operation == "store" else "acked")
                    and (operation != "ack" or response["acked"] is True), "CORRUPT_STORE")
                c.commit(); return dict(response, replayed=True)
            row = self._read_result(account, native_id, arena)
            if operation == "store":
                source = c.execute("SELECT * FROM p08b_reservation WHERE account_id=? AND reservation_id=?",
                    (account, request["reservation_id"])).fetchone()
                reservation = self._bound_reservation(account, native_id, arena, source)
                require(all(reservation[field] == request[field] for field in
                    ("run_id", "battle_id", "native_inventory_id", "reservation_id")), "RESULT_MISMATCH")
                self._match_result(results_value(request["results_json"]), reservation, native_id, arena)
                if row is None:
                    raw = request["results_json"]
                    c.execute("INSERT INTO p08c_result VALUES (?,?,?,?,?,0)", (account, arena,
                        request["reservation_id"], raw, sha(raw.encode("ascii"))))
                    self._failpoint("after_results_insert")
                    row = self._read_result(account, native_id, arena)
                else: require(row["reservation_id"] == request["reservation_id"] and row["results_json"] == request["results_json"], "RESULT_MISMATCH")
                status = "stored"
            elif operation == "ack" and row is not None:
                c.execute("UPDATE p08c_result SET acked=1 WHERE account_id=? AND arena_id=?", (account, arena))
                self._failpoint("after_results_ack"); row = self._read_result(account, native_id, arena); status = "acked"
            else: status = "missing" if row is None else "found"
            response = self._results_reply(request, status, row)
            if operation != "query" and row is not None:
                raw = canonical(response).decode("ascii")
                c.execute("INSERT INTO p08c_command VALUES (?,?,?,?,?,?)", (account, key, operation, payload_sha, raw, sha(raw.encode("ascii"))))
                self._failpoint("after_results_ledger")
            self._failpoint("before_results_commit"); c.commit(); return response
        except Exception:
            c.rollback(); raise


def results_service(store, request, *, authenticated_account_id):
    request = validate_request(request, authenticated_account_id)
    try: return store.results(request, authenticated_account_id=authenticated_account_id)
    except TransactionError as error:
        if error.code not in REJECTIONS: raise
        return store._results_reply(request, "rejected", code=error.code)
