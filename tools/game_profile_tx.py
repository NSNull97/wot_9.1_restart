"""Isolated P09B SQLite transaction harness.

This module deliberately owns one narrow server-side command: reserving a
vehicle for a battle.  It is a testable persistence boundary, not runtime
wiring, matchmaking, economy, or a client protocol implementation.

The store commits the vehicle snapshot and an exactly-once command ledger in a
single ``BEGIN IMMEDIATE`` transaction.  A command key can be replayed after
reopening the database; a changed payload, stale revision, unknown vehicle, or
already reserved vehicle fails closed without a partial write.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
from typing import Any, Iterable


SCHEMA = "p09b-game-profile.v1"
COMMAND = "reserve_vehicle"
MAX_ID = 96
MAX_PAYLOAD_BYTES = 16 * 1024
MAX_VEHICLES = 256
MAX_SNAPSHOT_BYTES = 256 * 1024


class TransactionError(RuntimeError):
    """A rejected command or a deliberately injected transaction failure."""

    def __init__(self, code: str, message: str | None = None):
        self.code = code
        super().__init__(f"{code}: {message}" if message else code)


def _bounded_id(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value or len(value) > MAX_ID:
        raise TransactionError("INVALID_INPUT", f"{label} must be a bounded non-empty string")
    if any(ord(char) < 0x21 or ord(char) > 0x7e for char in value):
        raise TransactionError("INVALID_INPUT", f"{label} must use visible ASCII")
    return value


def _revision(value: Any) -> int:
    if type(value) is not int or value < 0 or value > 2**31 - 1:
        raise TransactionError("INVALID_INPUT", "expected_revision must be a bounded integer")
    return value


def _canonical(value: Any) -> bytes:
    try:
        raw = json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError) as error:
        raise TransactionError("INVALID_INPUT", "payload is not canonical JSON") from error
    data = raw.encode("ascii")
    if len(data) > MAX_PAYLOAD_BYTES:
        raise TransactionError("INVALID_INPUT", "payload exceeds bounded size")
    return data


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _decode_object(raw: str, label: str) -> dict[str, Any]:
    try:
        raw_bytes = raw.encode("ascii")
    except UnicodeEncodeError as error:
        raise TransactionError("CORRUPT_STORE", f"{label} must be bounded ASCII JSON") from error
    if len(raw_bytes) > MAX_SNAPSHOT_BYTES:
        raise TransactionError("CORRUPT_STORE", f"{label} exceeds bounded size")

    def reject_constant(value: str) -> Any:
        raise ValueError(value)

    def unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result

    try:
        value = json.loads(raw, object_pairs_hook=unique_pairs, parse_constant=reject_constant)
    except (TypeError, ValueError) as error:
        raise TransactionError("CORRUPT_STORE", f"{label} is not JSON") from error
    if not isinstance(value, dict):
        raise TransactionError("CORRUPT_STORE", f"{label} must be an object")
    return value


class GameProfileStore:
    """Small, explicit SQLite store used only by the P09B harness."""

    def __init__(self, path: str | Path = ":memory:", *, failpoint: str | None = None):
        self.path = str(path)
        self.failpoint = failpoint
        self.connection = sqlite3.connect(self.path, timeout=2.0)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.connection.execute("PRAGMA busy_timeout = 2000")

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> "GameProfileStore":
        return self

    def __exit__(self, _type: Any, _value: Any, _traceback: Any) -> None:
        self.close()

    def initialize(self) -> None:
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS game_snapshot (
                account_id TEXT PRIMARY KEY,
                revision INTEGER NOT NULL CHECK (revision >= 0),
                snapshot_json TEXT NOT NULL,
                snapshot_sha256 TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS game_vehicle (
                account_id TEXT NOT NULL REFERENCES game_snapshot(account_id)
                    ON DELETE CASCADE,
                vehicle_id TEXT NOT NULL,
                state TEXT NOT NULL CHECK (state IN ('available', 'reserved')),
                battle_id TEXT,
                PRIMARY KEY (account_id, vehicle_id),
                CHECK ((state = 'available' AND battle_id IS NULL) OR
                       (state = 'reserved' AND battle_id IS NOT NULL))
            );
            CREATE TABLE IF NOT EXISTS game_command_ledger (
                account_id TEXT NOT NULL,
                command_id TEXT NOT NULL,
                command_type TEXT NOT NULL,
                payload_sha256 TEXT NOT NULL,
                source_revision INTEGER NOT NULL,
                destination_revision INTEGER NOT NULL,
                result_json TEXT NOT NULL,
                PRIMARY KEY (account_id, command_id),
                FOREIGN KEY (account_id) REFERENCES game_snapshot(account_id)
                    ON DELETE CASCADE
            );
            """
        )
        self.connection.commit()

    def create_profile(self, account_id: str, vehicles: Iterable[str]) -> None:
        account_id = _bounded_id(account_id, "account_id")
        vehicle_ids = [_bounded_id(vehicle, "vehicle_id") for vehicle in vehicles]
        if not vehicle_ids or len(vehicle_ids) > MAX_VEHICLES or len(set(vehicle_ids)) != len(vehicle_ids):
            raise TransactionError("INVALID_INPUT", "vehicles must be unique and bounded")
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            if self.connection.execute(
                "SELECT 1 FROM game_snapshot WHERE account_id = ?", (account_id,)
            ).fetchone():
                raise TransactionError("ALREADY_EXISTS")
            snapshot = self._snapshot(account_id, 0, [(vehicle, "available", None) for vehicle in vehicle_ids])
            self.connection.execute(
                "INSERT INTO game_snapshot(account_id, revision, snapshot_json, snapshot_sha256) VALUES (?, 0, ?, ?)",
                (account_id, snapshot[0], snapshot[1]),
            )
            self.connection.executemany(
                "INSERT INTO game_vehicle(account_id, vehicle_id, state, battle_id) VALUES (?, ?, 'available', NULL)",
                [(account_id, vehicle) for vehicle in vehicle_ids],
            )
            self.connection.commit()
        except Exception:
            self.connection.rollback()
            raise

    def _snapshot(
        self,
        account_id: str,
        revision: int,
        vehicles: Iterable[tuple[str, str, str | None]],
    ) -> tuple[str, str]:
        vehicle_rows = [
            {"battle_id": battle_id, "state": state, "vehicle_id": vehicle_id}
            for vehicle_id, state, battle_id in sorted(vehicles)
        ]
        value = {"account_id": account_id, "revision": revision, "vehicles": vehicle_rows}
        raw = _canonical(value)
        if len(raw) > MAX_SNAPSHOT_BYTES:
            raise TransactionError("CORRUPT_STORE", "snapshot exceeds bounded size")
        return raw.decode("ascii"), _sha(raw)

    def _failpoint(self, name: str) -> None:
        if self.failpoint == name:
            raise TransactionError("INJECTED_FAILURE", name)

    def _result_from_row(self, row: sqlite3.Row) -> dict[str, Any]:
        try:
            result = _decode_object(row["result_json"], "ledger result")
        except TransactionError:
            raise
        result["replayed"] = True
        return result

    def reserve_vehicle(
        self,
        *,
        account_id: str,
        command_id: str,
        vehicle_id: str,
        expected_revision: int,
        battle_id: str,
    ) -> dict[str, Any]:
        account_id = _bounded_id(account_id, "account_id")
        command_id = _bounded_id(command_id, "command_id")
        vehicle_id = _bounded_id(vehicle_id, "vehicle_id")
        battle_id = _bounded_id(battle_id, "battle_id")
        expected_revision = _revision(expected_revision)
        payload = {
            "account_id": account_id,
            "battle_id": battle_id,
            "command": COMMAND,
            "expected_revision": expected_revision,
            "vehicle_id": vehicle_id,
        }
        payload_sha256 = _sha(_canonical(payload))
        connection = self.connection
        connection.execute("BEGIN IMMEDIATE")
        try:
            ledger = connection.execute(
                "SELECT * FROM game_command_ledger WHERE account_id = ? AND command_id = ?",
                (account_id, command_id),
            ).fetchone()
            if ledger is not None:
                if ledger["command_type"] != COMMAND or ledger["payload_sha256"] != payload_sha256:
                    raise TransactionError("DUPLICATE_PAYLOAD_MISMATCH")
                result = self._result_from_row(ledger)
                connection.commit()
                return result

            snapshot_row = connection.execute(
                "SELECT * FROM game_snapshot WHERE account_id = ?", (account_id,)
            ).fetchone()
            if snapshot_row is None:
                raise TransactionError("UNKNOWN_ACCOUNT")
            actual_revision = int(snapshot_row["revision"])
            if expected_revision != actual_revision:
                raise TransactionError("STALE_REVISION")
            vehicle = connection.execute(
                "SELECT * FROM game_vehicle WHERE account_id = ? AND vehicle_id = ?",
                (account_id, vehicle_id),
            ).fetchone()
            if vehicle is None:
                raise TransactionError("UNKNOWN_VEHICLE")
            if vehicle["state"] != "available":
                raise TransactionError("VEHICLE_RESERVED")

            destination_revision = actual_revision + 1
            connection.execute(
                "UPDATE game_vehicle SET state = 'reserved', battle_id = ? WHERE account_id = ? AND vehicle_id = ?",
                (battle_id, account_id, vehicle_id),
            )
            self._failpoint("after_vehicle_update")
            rows = connection.execute(
                "SELECT vehicle_id, state, battle_id FROM game_vehicle WHERE account_id = ? ORDER BY vehicle_id",
                (account_id,),
            ).fetchall()
            snapshot_json, snapshot_sha256 = self._snapshot(
                account_id,
                destination_revision,
                [(row["vehicle_id"], row["state"], row["battle_id"]) for row in rows],
            )
            connection.execute(
                "UPDATE game_snapshot SET revision = ?, snapshot_json = ?, snapshot_sha256 = ? WHERE account_id = ?",
                (destination_revision, snapshot_json, snapshot_sha256, account_id),
            )
            result = {
                "account_id": account_id,
                "battle_id": battle_id,
                "command": COMMAND,
                "command_id": command_id,
                "destination_revision": destination_revision,
                "replayed": False,
                "source_revision": actual_revision,
                "status": "reserved",
                "vehicle_id": vehicle_id,
            }
            result_json = _canonical(result).decode("ascii")
            connection.execute(
                "INSERT INTO game_command_ledger(account_id, command_id, command_type, payload_sha256, source_revision, destination_revision, result_json) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (account_id, command_id, COMMAND, payload_sha256, actual_revision, destination_revision, result_json),
            )
            self._failpoint("before_commit")
            connection.commit()
            return result
        except Exception:
            connection.rollback()
            raise

    def read_profile(self, account_id: str) -> dict[str, Any]:
        account_id = _bounded_id(account_id, "account_id")
        row = self.connection.execute(
            "SELECT * FROM game_snapshot WHERE account_id = ?", (account_id,)
        ).fetchone()
        if row is None:
            raise TransactionError("UNKNOWN_ACCOUNT")
        raw = row["snapshot_json"].encode("ascii")
        if _sha(raw) != row["snapshot_sha256"]:
            raise TransactionError("CORRUPT_STORE", "snapshot digest mismatch")
        value = _decode_object(row["snapshot_json"], "snapshot")
        if value.get("revision") != row["revision"]:
            raise TransactionError("CORRUPT_STORE", "snapshot revision mismatch")
        expected_vehicles = [
            {"battle_id": vehicle["battle_id"], "state": vehicle["state"], "vehicle_id": vehicle["vehicle_id"]}
            for vehicle in self.connection.execute(
                "SELECT vehicle_id, state, battle_id FROM game_vehicle WHERE account_id = ? ORDER BY vehicle_id",
                (account_id,),
            ).fetchall()
        ]
        expected = {"account_id": account_id, "revision": int(row["revision"]), "vehicles": expected_vehicles}
        if value != expected:
            raise TransactionError("CORRUPT_STORE", "snapshot does not match vehicle rows")
        return value

    def ledger_count(self, account_id: str) -> int:
        return int(self.connection.execute(
            "SELECT COUNT(*) FROM game_command_ledger WHERE account_id = ?", (account_id,)
        ).fetchone()[0])


def _run_self_check(receipt_path: Path | None) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="p09b-tx-") as directory:
        db_path = Path(directory) / "profile.sqlite3"
        with GameProfileStore(db_path) as store:
            store.initialize()
            store.create_profile("acct-test", ("ms1", "is7"))
            first = store.reserve_vehicle(
                account_id="acct-test", command_id="cmd-1", vehicle_id="is7",
                expected_revision=0, battle_id="battle-a",
            )
            replay = store.reserve_vehicle(
                account_id="acct-test", command_id="cmd-1", vehicle_id="is7",
                expected_revision=0, battle_id="battle-a",
            )
            checks = {"duplicate_replay": first == {**replay, "replayed": False}}
            try:
                store.reserve_vehicle(account_id="acct-test", command_id="cmd-1", vehicle_id="is7", expected_revision=0, battle_id="battle-b")
            except TransactionError as error:
                checks["duplicate_payload_mismatch"] = error.code == "DUPLICATE_PAYLOAD_MISMATCH"
            try:
                store.reserve_vehicle(account_id="acct-test", command_id="cmd-stale", vehicle_id="ms1", expected_revision=0, battle_id="battle-b")
            except TransactionError as error:
                checks["stale_revision"] = error.code == "STALE_REVISION"
            try:
                store.reserve_vehicle(account_id="acct-test", command_id="cmd-unknown", vehicle_id="is6", expected_revision=1, battle_id="battle-b")
            except TransactionError as error:
                checks["unknown_vehicle"] = error.code == "UNKNOWN_VEHICLE"
            try:
                store.reserve_vehicle(account_id="acct-test", command_id="cmd-reserved", vehicle_id="is7", expected_revision=1, battle_id="battle-b")
            except TransactionError as error:
                checks["reserved_vehicle"] = error.code == "VEHICLE_RESERVED"
        with GameProfileStore(db_path, failpoint="after_vehicle_update") as store:
            store.initialize()
            try:
                store.reserve_vehicle(account_id="acct-test", command_id="cmd-rollback", vehicle_id="ms1", expected_revision=1, battle_id="battle-b")
            except TransactionError as error:
                checks["rollback_injected"] = error.code == "INJECTED_FAILURE"
        with GameProfileStore(db_path) as store:
            store.initialize()
            profile = store.read_profile("acct-test")
            checks["reopen_preserves_atomic_state"] = (
                profile["revision"] == 1
                and all(vehicle["state"] == "available" for vehicle in profile["vehicles"] if vehicle["vehicle_id"] == "ms1")
                and store.ledger_count("acct-test") == 1
            )
            checks["all"] = all(checks.values())
            result = {"schema": SCHEMA, "status": "PASS_P09B_SQLITE_TRANSACTION_HARNESS" if checks["all"] else "FAIL", "checks": checks, "revision_after_reopen": profile["revision"], "ledger_rows_after_reopen": store.ledger_count("acct-test")}
    if receipt_path is not None:
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        receipt_path.write_text(json.dumps(result, ensure_ascii=True, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the isolated P09B SQLite transaction self-check")
    parser.add_argument("--self-check", action="store_true", help="run the bounded harness receipt")
    parser.add_argument("--receipt", type=Path, help="write the JSON receipt to this path")
    args = parser.parse_args(argv)
    if not args.self_check:
        parser.error("--self-check is required; this module has no runtime server mode")
    result = _run_self_check(args.receipt)
    print(json.dumps(result, ensure_ascii=True, sort_keys=True))
    return 0 if result["status"] == "PASS_P09B_SQLITE_TRANSACTION_HARNESS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
