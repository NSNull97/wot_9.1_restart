"""P09C isolated ammunition service extending the P09B store, never live wiring.

Only owned depot shells can be moved. Prices/purchases are unsupported. The
authenticated subject and server command ID must come from a trusted caller.
The existing P09B reservation, aggregate revision and ledger remain shared.
"""
from __future__ import annotations

import json
from typing import Any, Iterable

from game_profile_tx import (
    GameProfileStore, TransactionError, _bounded_id, _canonical,
    _decode_object, _revision, _sha,
)
from p09c_ammo_catalog import MOUNTS, SHELLS, CATALOG_SHA256

SCHEMA = "p09c-ammo-service.v1"
COMMAND = "p09c.set_ammunition.v1"
MAX_DEPOT = 1_000_000  # Harness policy, not a historical inventory limit.
MAX_OWNED = 16
MAX_JSON = 16 * 1024


def _quantity(value: Any, maximum: int = MAX_DEPOT) -> int:
    if type(value) is not int or not 0 <= value <= maximum:
        raise TransactionError("INVALID_QUANTITY")
    return value


def _quantities(value: Any, allowed: Iterable[str]) -> dict[str, int]:
    allowed = tuple(allowed)
    if type(value) is not dict or len(value) > len(allowed):
        raise TransactionError("INVALID_INPUT", "bounded shell map required")
    if any(type(key) is not str or key not in allowed for key in value):
        raise TransactionError("INCOMPATIBLE_SHELL")
    return {key: _quantity(value.get(key, 0)) for key in sorted(allowed)}


def _object(raw: str) -> dict:
    """Bound nesting before the existing duplicate/nonfinite JSON decoder."""
    if type(raw) is not str or len(raw) > MAX_JSON:
        raise TransactionError("CORRUPT_STORE", "JSON bound")
    depth, quoted, escaped = 0, False, False
    for char in raw:
        if quoted:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
        elif char == '"':
            quoted = True
        elif char in "[{":
            depth += 1
            if depth > 8:
                raise TransactionError("CORRUPT_STORE", "JSON depth")
        elif char in "]}":
            depth -= 1
    return _decode_object(raw, "P09C object")


class AmmoServiceStore(GameProfileStore):
    """Versioned test extension; use this class for every writer of this DB.

    The inherited reserve_vehicle method uses the overridden snapshot hooks,
    so reservation and servicing share one revision and command-key namespace.
    This is not a migration for old harness files or the deployed game store.
    """

    def initialize(self) -> None:
        connection = self.connection
        existing = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
        names = {row[0] for row in existing}
        if names:
            if "p09c_schema" not in names:
                raise TransactionError("UNSUPPORTED_STORE_SCHEMA")
            markers = connection.execute("SELECT version FROM p09c_schema").fetchall()
            if [row[0] for row in markers] != [SCHEMA]:
                raise TransactionError("UNSUPPORTED_STORE_SCHEMA")
            if not {"game_snapshot", "game_vehicle", "game_command_ledger",
                    "p09c_ammo_mount", "p09c_ammo_depot"} <= names:
                raise TransactionError("CORRUPT_STORE", "missing extension table")
            columns = {row[1] for row in connection.execute("PRAGMA table_info(game_command_ledger)")}
            if "p09c_result_sha256" not in columns:
                raise TransactionError("CORRUPT_STORE", "missing result integrity column")
            return
        super().initialize()
        connection.executescript("""
            ALTER TABLE game_command_ledger ADD COLUMN p09c_result_sha256 TEXT;
            CREATE TABLE p09c_schema (version TEXT PRIMARY KEY);
            CREATE TABLE p09c_ammo_mount (
                account_id TEXT NOT NULL,
                vehicle_id TEXT NOT NULL,
                mount_id TEXT NOT NULL,
                loaded_json TEXT NOT NULL,
                PRIMARY KEY(account_id, vehicle_id),
                FOREIGN KEY(account_id, vehicle_id)
                    REFERENCES game_vehicle(account_id, vehicle_id)
            );
            CREATE TABLE p09c_ammo_depot (
                account_id TEXT NOT NULL REFERENCES game_snapshot(account_id),
                shell_id TEXT NOT NULL,
                quantity INTEGER NOT NULL CHECK(quantity >= 0 AND quantity <= 1000000),
                PRIMARY KEY(account_id, shell_id)
            );
        """)
        connection.execute("INSERT INTO p09c_schema(version) VALUES (?)", (SCHEMA,))
        connection.commit()

    def create_profile(self, account_id: str, vehicles: Iterable[str]) -> None:
        # A bounded materialization also rejects unbounded iterators promptly.
        iterator = iter(vehicles)
        vehicle_ids = []
        for _ in range(MAX_OWNED + 1):
            try:
                vehicle_ids.append(next(iterator))
            except StopIteration:
                break
        if len(vehicle_ids) > MAX_OWNED:
            raise TransactionError("INVALID_INPUT", "vehicle count")
        super().create_profile(account_id, vehicle_ids)

    def _ammo_projection(self, account_id: str) -> tuple[list[dict], dict]:
        mounts = self.connection.execute(
            "SELECT vehicle_id, mount_id, loaded_json FROM p09c_ammo_mount "
            "WHERE account_id = ? ORDER BY vehicle_id LIMIT ?", (account_id, MAX_OWNED + 1)
        ).fetchall()
        depot_rows = self.connection.execute(
            "SELECT shell_id, quantity FROM p09c_ammo_depot "
            "WHERE account_id = ? ORDER BY shell_id LIMIT ?", (account_id, len(SHELLS) + 1)
        ).fetchall()
        if len(mounts) > MAX_OWNED or len(depot_rows) > len(SHELLS):
            raise TransactionError("CORRUPT_STORE", "row bound")
        ammunition = []
        try:
            for row in mounts:
                mount = MOUNTS.get(row["mount_id"])
                if mount is None:
                    raise TransactionError("CORRUPT_STORE", "unknown mounted configuration")
                raw = _object(row["loaded_json"])
                loaded = _quantities(raw, mount.shell_ids)
                if set(raw) != set(loaded) or sum(loaded.values()) > mount.capacity:
                    raise TransactionError("CORRUPT_STORE", "loaded projection")
                ammunition.append({"vehicle_id": row["vehicle_id"],
                                   "mount_id": row["mount_id"], "loaded": loaded})
            depot = {row["shell_id"]: row["quantity"] for row in depot_rows}
            if mounts:
                if set(depot) != set(SHELLS):
                    raise TransactionError("CORRUPT_STORE", "depot projection")
                depot = _quantities(depot, SHELLS)
            elif depot:
                raise TransactionError("CORRUPT_STORE", "depot without mounted configuration")
        except TransactionError as error:
            raise TransactionError("CORRUPT_STORE", str(error)) from error
        return ammunition, depot

    def _snapshot(self, account_id, revision, vehicles):
        _revision(revision)  # Also bounds inherited reserve_vehicle's increment.
        vehicles = list(vehicles)
        if len(vehicles) > MAX_OWNED:
            raise TransactionError("CORRUPT_STORE", "vehicle count")
        raw, _digest = super()._snapshot(account_id, revision, vehicles)
        value = json.loads(raw)  # Our own bounded primitive encoder output.
        ammunition, depot = self._ammo_projection(account_id)
        if ammunition and {row["vehicle_id"] for row in ammunition} != {row[0] for row in vehicles}:
            raise TransactionError("CORRUPT_STORE", "mounted ownership projection")
        value.update(schema=SCHEMA, catalog_sha256=CATALOG_SHA256,
                     ammunition=ammunition, depot=depot)
        encoded = _canonical(value)
        return encoded.decode("ascii"), _sha(encoded)

    def _verified_snapshot(self, row, account_id):
        value = _object(row["snapshot_json"])
        try:
            revision = _revision(row["revision"])
            vehicles = self.connection.execute(
                "SELECT vehicle_id, state, battle_id FROM game_vehicle "
                "WHERE account_id = ? ORDER BY vehicle_id LIMIT ?", (account_id, MAX_OWNED + 1)
            ).fetchall()
            expected, digest = self._snapshot(account_id, revision, [tuple(v) for v in vehicles])
        except TransactionError as error:
            raise TransactionError("CORRUPT_STORE", str(error)) from error
        if row["snapshot_json"] != expected or row["snapshot_sha256"] != digest:
            raise TransactionError("CORRUPT_STORE", "snapshot digest/projection/schema mismatch")
        return value

    def read_profile(self, account_id: str) -> dict:
        # Snapshot and all row projections must see the same SQLite read view.
        if self.connection.in_transaction:
            return super().read_profile(account_id)
        self.connection.execute("BEGIN")
        try:
            result = super().read_profile(account_id)
            self.connection.commit()
            return result
        except Exception:
            self.connection.rollback()
            raise

    def _save_snapshot(self, account_id: str, revision: int) -> None:
        rows = self.connection.execute(
            "SELECT vehicle_id, state, battle_id FROM game_vehicle "
            "WHERE account_id = ? ORDER BY vehicle_id LIMIT ?", (account_id, MAX_OWNED + 1)
        ).fetchall()
        raw, digest = self._snapshot(account_id, revision, [tuple(row) for row in rows])
        self.connection.execute(
            "UPDATE game_snapshot SET revision = ?, snapshot_json = ?, snapshot_sha256 = ? WHERE account_id = ?",
            (revision, raw, digest, account_id),
        )

    def _result_from_row(self, row) -> dict:
        """Bound and verify inherited P09B reservation replay before success."""
        result = _object(row["result_json"])
        required = {"account_id", "battle_id", "command", "command_id", "destination_revision",
                    "replayed", "source_revision", "status", "vehicle_id"}
        if set(result) != required:
            raise TransactionError("CORRUPT_STORE", "reservation result shape")
        try:
            for key in ("account_id", "battle_id", "command_id", "vehicle_id"):
                _bounded_id(result[key], key)
            source = _revision(result["source_revision"])
            destination = _revision(result["destination_revision"])
        except TransactionError as error:
            raise TransactionError("CORRUPT_STORE", str(error)) from error
        profile = self.read_profile(row["account_id"])
        payload = {"account_id": result["account_id"], "battle_id": result["battle_id"],
                   "command": result["command"], "expected_revision": source,
                   "vehicle_id": result["vehicle_id"]}
        if (result["account_id"] != row["account_id"] or result["command_id"] != row["command_id"]
                or result["command"] != "reserve_vehicle" or row["command_type"] != "reserve_vehicle"
                or result["status"] != "reserved" or result["replayed"] is not False
                or row["source_revision"] != source or row["destination_revision"] != destination
                or destination != source + 1 or destination > profile["revision"]
                or _sha(_canonical(payload)) != row["payload_sha256"]):
            raise TransactionError("CORRUPT_STORE", "reservation result binding")
        return {**result, "replayed": True}

    def seed_test_ammunition(self, account_id: str, mounts: dict[str, str], depot: dict[str, int]) -> None:
        """One-time isolated fixture bootstrap, not a grant/purchase command.

        Creates empty tank loads and explicit already-owned test depot stock.
        There must be no command history and every owned vehicle must be bound.
        """
        account_id = _bounded_id(account_id, "account_id")
        if type(mounts) is not dict or not 1 <= len(mounts) <= MAX_OWNED:
            raise TransactionError("INVALID_INPUT")
        for vehicle_id, mount_id in mounts.items():
            _bounded_id(vehicle_id, "vehicle_id")
            if type(mount_id) is not str or mount_id not in MOUNTS:
                raise TransactionError("UNSUPPORTED_MOUNT")
        depot = _quantities(depot, SHELLS)
        connection = self.connection
        connection.execute("BEGIN IMMEDIATE")
        try:
            profile = self.read_profile(account_id)
            if profile["revision"] != 0 or profile["ammunition"] or self.ledger_count(account_id):
                raise TransactionError("ALREADY_SEEDED_OR_USED")
            if set(mounts) != {row["vehicle_id"] for row in profile["vehicles"]}:
                raise TransactionError("UNKNOWN_VEHICLE")
            for vehicle_id, mount_id in sorted(mounts.items()):
                loaded = _quantities({}, MOUNTS[mount_id].shell_ids)
                connection.execute("INSERT INTO p09c_ammo_mount VALUES (?, ?, ?, ?)",
                                   (account_id, vehicle_id, mount_id, _canonical(loaded).decode("ascii")))
            connection.executemany("INSERT INTO p09c_ammo_depot VALUES (?, ?, ?)",
                                   [(account_id, shell_id, quantity) for shell_id, quantity in depot.items()])
            self._save_snapshot(account_id, 0)
            self._failpoint("before_seed_commit")
            connection.commit()
        except Exception:
            connection.rollback()
            raise

    def set_ammunition(self, *, authenticated_account_id: str, account_id: str,
                       command_id: str, vehicle_id: str, expected_revision: int,
                       desired: dict[str, int], funding: str = "owned_depot") -> dict:
        """Set absolute load, unloading omitted types, under the shared ledger.

        Mount and capacity are read from the server-owned aggregate. The caller
        cannot pick a gun, prices, stock, revision result or native shell bytes.
        """
        authenticated_account_id = _bounded_id(authenticated_account_id, "authenticated_account_id")
        account_id = _bounded_id(account_id, "account_id")
        if authenticated_account_id != account_id:
            raise TransactionError("FOREIGN_ACCOUNT")
        command_id = _bounded_id(command_id, "command_id")
        vehicle_id = _bounded_id(vehicle_id, "vehicle_id")
        expected_revision = _revision(expected_revision)
        if funding != "owned_depot":
            raise TransactionError("PURCHASE_UNSUPPORTED")
        requested = _quantities(desired, SHELLS)
        # Canonicalize only explicit shell keys: explicit incompatible zeros
        # must be rejected, while omitted compatible shells mean unload.
        desired = {key: requested[key] for key in sorted(desired)}
        payload = {"schema": SCHEMA, "catalog_sha256": CATALOG_SHA256, "command": COMMAND,
                   "account_id": account_id, "vehicle_id": vehicle_id,
                   "expected_revision": expected_revision, "desired": desired,
                   "funding": funding}
        payload_sha = _sha(_canonical(payload))
        connection = self.connection
        connection.execute("BEGIN IMMEDIATE")
        try:
            # Verify current aggregate even for replays: corruption is not success.
            profile = self.read_profile(account_id)
            ledger = connection.execute(
                "SELECT * FROM game_command_ledger WHERE account_id = ? AND command_id = ?",
                (account_id, command_id),
            ).fetchone()
            if ledger is not None:
                if ledger["command_type"] != COMMAND or ledger["payload_sha256"] != payload_sha:
                    raise TransactionError("DUPLICATE_PAYLOAD_MISMATCH")
                result = self._verified_replay(ledger, payload, command_id)
                if result["destination_revision"] > profile["revision"]:
                    raise TransactionError("CORRUPT_STORE", "ledger ahead of aggregate")
                connection.commit()
                return result
            if profile["revision"] != expected_revision:
                raise TransactionError("STALE_REVISION")
            if expected_revision == 2**31 - 1:
                raise TransactionError("REVISION_EXHAUSTED")
            vehicle = next((v for v in profile["vehicles"] if v["vehicle_id"] == vehicle_id), None)
            if vehicle is None:
                raise TransactionError("UNKNOWN_VEHICLE")
            if vehicle["state"] != "available":
                raise TransactionError("VEHICLE_RESERVED")
            ammunition = next((v for v in profile["ammunition"] if v["vehicle_id"] == vehicle_id), None)
            if ammunition is None:
                raise TransactionError("UNSUPPORTED_MOUNT")
            mount = MOUNTS[ammunition["mount_id"]]
            loaded = _quantities(desired, mount.shell_ids)
            if sum(loaded.values()) > mount.capacity:
                raise TransactionError("CAPACITY_EXCEEDED")
            depot = dict(profile["depot"])
            delta = {}
            for shell_id in mount.shell_ids:
                delta[shell_id] = loaded[shell_id] - ammunition["loaded"][shell_id]
                remaining = depot[shell_id] - delta[shell_id]
                if remaining < 0:
                    raise TransactionError("INSUFFICIENT_STOCK")
                if remaining > MAX_DEPOT:
                    raise TransactionError("DEPOT_OVERFLOW")
                depot[shell_id] = remaining
            connection.executemany(
                "UPDATE p09c_ammo_depot SET quantity = ? WHERE account_id = ? AND shell_id = ?",
                [(quantity, account_id, shell_id) for shell_id, quantity in depot.items()],
            )
            self._failpoint("after_depot_update")
            connection.execute(
                "UPDATE p09c_ammo_mount SET loaded_json = ? WHERE account_id = ? AND vehicle_id = ?",
                (_canonical(loaded).decode("ascii"), account_id, vehicle_id),
            )
            self._failpoint("after_ammo_update")
            self._save_snapshot(account_id, expected_revision + 1)
            self._failpoint("after_snapshot_update")
            result = {"schema": SCHEMA, "catalog_sha256": CATALOG_SHA256, "command": COMMAND,
                      "account_id": account_id, "vehicle_id": vehicle_id, "command_id": command_id,
                      "source_revision": expected_revision, "destination_revision": expected_revision + 1,
                      "mount_id": mount.mount_id, "loaded": loaded, "depot_delta": {k: -v for k, v in delta.items()},
                      "status": "serviced", "financial_status": "UNSUPPORTED", "replayed": False}
            connection.execute(
                "INSERT INTO game_command_ledger(account_id, command_id, command_type, payload_sha256, "
                "source_revision, destination_revision, result_json, p09c_result_sha256) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (account_id, command_id, COMMAND, payload_sha, expected_revision, expected_revision + 1,
                 _canonical(result).decode("ascii"), _sha(_canonical(result))),
            )
            self._failpoint("before_commit")
            connection.commit()
            return result
        except Exception:
            connection.rollback()
            raise

    def _verified_replay(self, row, payload: dict, command_id: str) -> dict:
        result = _object(row["result_json"])
        if _sha(_canonical(result)) != row["p09c_result_sha256"]:
            raise TransactionError("CORRUPT_STORE", "ledger result digest")
        mount = MOUNTS.get(result.get("mount_id")) if type(result.get("mount_id")) is str else None
        required = {"schema", "catalog_sha256", "command", "account_id", "vehicle_id", "command_id",
                    "source_revision", "destination_revision", "mount_id", "loaded", "depot_delta",
                    "status", "financial_status", "replayed"}
        if set(result) != required or mount is None:
            raise TransactionError("CORRUPT_STORE", "ledger result shape")
        for key in ("schema", "catalog_sha256", "command", "account_id", "vehicle_id"):
            if result[key] != payload[key]:
                raise TransactionError("CORRUPT_STORE", "ledger result binding")
        try:
            loaded = _quantities(payload["desired"], mount.shell_ids)
            source = _revision(result["source_revision"])
            destination = _revision(result["destination_revision"])
        except TransactionError as error:
            raise TransactionError("CORRUPT_STORE", str(error)) from error
        delta = result["depot_delta"]
        if (result["command_id"] != command_id or source != payload["expected_revision"]
                or row["source_revision"] != source or row["destination_revision"] != destination
                or destination != source + 1 or result["replayed"] is not False
                or result["status"] != "serviced" or result["financial_status"] != "UNSUPPORTED"
                or _canonical(result["loaded"]) != _canonical(loaded) or sum(loaded.values()) > mount.capacity
                or type(delta) is not dict or set(delta) != set(mount.shell_ids)
                or any(type(v) is not int or abs(v) > mount.capacity for v in delta.values())):
            raise TransactionError("CORRUPT_STORE", "ledger result invariant")
        return {**result, "replayed": True}
