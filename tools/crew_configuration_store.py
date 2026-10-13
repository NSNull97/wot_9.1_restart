"""Source-bound configuration reservation on the existing P09B/P09C store.

Isolated integration harness only. All writers must use this subclass. The
fixture seed is not an equipment inventory/grant API or a deployed migration.
Actual source activation precedes opening SQLite; no native client is run.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
# The retained P09B/P09C tools use their historical script-level imports.
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from game_profile_tx import TransactionError, _bounded_id, _canonical, _revision, _sha
from p09c_ammo_service import AmmoServiceStore, MAX_OWNED, _object
from p09c_ammo_catalog import CATALOG_SHA256, MOUNTS, audit_sources
from tools.crew_equipment_mass import load_verified_assemblies, _configured_paths
from tools.crew_equipment_source_audit import audit as audit_crew_sources
from server.domain import crew_equipment as crew

SCHEMA = "crew-configuration-store.v1"
COMMAND = "reserve_configuration.v1"


def _id(value, label):
    _bounded_id(value, label)
    try:
        crew._identifier(value, label)
    except crew.ConfigurationError as error:
        raise TransactionError("INVALID_INPUT", str(error)) from error
    return value


def _digest(value):
    try:
        crew._digest(value, "expected_configuration_sha256")
    except crew.ConfigurationError as error:
        raise TransactionError("INVALID_INPUT", str(error)) from error
    return value


class ConfigurationStore(AmmoServiceStore):
    """One connection, aggregate revision and ledger; no nested transactions.

    Configuration revision starts at 1 and is immutable in this card. The
    P09C aggregate revision starts at 0 and advances for ammo/reservation.
    Authentication remains the trusted caller's job; the subject is checked
    before replay. No public command accepts crew, modules or modifiers.
    """

    def __init__(self, path, *, config_path, failpoint=None):
        assemblies = load_verified_assemblies(config_path)
        self.assemblies = {item.mount_id: item for item in assemblies}
        self.crew_source_receipt = audit_crew_sources(config_path)
        original, _local = _configured_paths(config_path)
        self.ammo_source_receipt = audit_sources(original)
        super().__init__(path, failpoint=failpoint)

    def initialize(self):
        names = {row[0] for row in self.connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if names:
            if "crew_configuration_schema" not in names:
                raise TransactionError("UNSUPPORTED_STORE_SCHEMA")
            if [row[0] for row in self.connection.execute("SELECT version FROM crew_configuration_schema")] != [SCHEMA]:
                raise TransactionError("UNSUPPORTED_STORE_SCHEMA")
            if "crew_vehicle_configuration" not in names:
                raise TransactionError("CORRUPT_STORE", "configuration table missing")
            super().initialize()
            return
        super().initialize()
        self.connection.executescript("""
            CREATE TABLE crew_configuration_schema(version TEXT PRIMARY KEY);
            CREATE TABLE crew_vehicle_configuration(
                account_id TEXT NOT NULL,
                vehicle_id TEXT NOT NULL,
                configuration_revision INTEGER NOT NULL CHECK(configuration_revision = 1),
                configuration_json TEXT NOT NULL,
                configuration_sha256 TEXT NOT NULL,
                PRIMARY KEY(account_id, vehicle_id),
                FOREIGN KEY(account_id, vehicle_id) REFERENCES game_vehicle(account_id, vehicle_id)
            );
        """)
        self.connection.execute("INSERT INTO crew_configuration_schema VALUES (?)", (SCHEMA,))
        self.connection.commit()

    def create_profile(self, account_id, vehicles):
        _id(account_id, "account_id")
        # Keep the inherited bounded iteration; validate identifiers afterwards
        # in a bounded materialization before any mutation.
        iterator, selected = iter(vehicles), []
        for _ in range(MAX_OWNED + 1):
            try:
                selected.append(_id(next(iterator), "vehicle_id"))
            except StopIteration:
                break
        super().create_profile(account_id, selected)

    def _configuration(self, account_id, vehicle_id, row, ammo):
        if ammo is None or ammo["mount_id"] not in self.assemblies:
            raise TransactionError("CONFIGURATION_MOUNT_MISMATCH")
        assembly = self.assemblies[ammo["mount_id"]]
        mount = MOUNTS[ammo["mount_id"]]
        if mount.vehicle_definition_id != assembly.vehicle_definition_id:
            raise TransactionError("CONFIGURATION_MOUNT_MISMATCH")
        if type(row["configuration_revision"]) is not int or row["configuration_revision"] != 1:
            raise TransactionError("CORRUPT_STORE", "configuration revision")
        raw = row["configuration_json"]
        if type(raw) is not str or len(raw) > crew.MAX_BYTES:
            raise TransactionError("CORRUPT_STORE", "configuration byte bound")
        try:
            encoded = raw.encode("ascii")
            value = _object(raw)
            if value.get("vehicle_definition_id") != mount.vehicle_definition_id:
                raise TransactionError("CONFIGURATION_MOUNT_MISMATCH")
            binding = crew.TrustedBinding(account_id, vehicle_id, row["configuration_revision"],
                row["configuration_sha256"], assembly.component_configuration_sha256,
                crew.POLICY_SHA256, assembly.mass_budget)
            return crew.build_snapshot(encoded, binding=binding)
        except (crew.ConfigurationError, UnicodeError) as error:
            raise TransactionError("INVALID_CONFIGURATION", str(error)) from error

    def _configurations(self, account_id, ammunition):
        rows = self.connection.execute(
            "SELECT * FROM crew_vehicle_configuration WHERE account_id=? ORDER BY vehicle_id LIMIT ?",
            (account_id, MAX_OWNED + 1)).fetchall()
        if len(rows) > MAX_OWNED:
            raise TransactionError("CORRUPT_STORE", "configuration count")
        seen, result = set(), []
        for row in rows:
            ammo = next((a for a in ammunition if a["vehicle_id"] == row["vehicle_id"]), None)
            snapshot = self._configuration(account_id, row["vehicle_id"], row, ammo)
            data = snapshot.as_dict()
            for member in data["crew"]:
                if member["crew_id"] in seen:
                    raise TransactionError("DUPLICATE_CREW_ASSIGNMENT")
                seen.add(member["crew_id"])
            result.append({"vehicle_id": row["vehicle_id"], "configuration_revision": row["configuration_revision"],
                           "configuration_sha256": row["configuration_sha256"],
                           "component_configuration_sha256": data["component_configuration_sha256"],
                           "snapshot_sha256": snapshot.sha256})
        return result

    def _snapshot(self, account_id, revision, vehicles):
        vehicles = list(vehicles)
        raw, _ = super()._snapshot(account_id, revision, vehicles)
        value = _object(raw)
        configs = self._configurations(account_id, value["ammunition"])
        if configs and {c["vehicle_id"] for c in configs} != {v[0] for v in vehicles}:
            raise TransactionError("CORRUPT_STORE", "incomplete configuration ownership projection")
        value.update(configuration_schema=SCHEMA, crew_policy_sha256=crew.POLICY_SHA256, configurations=configs)
        data = _canonical(value)
        return data.decode("ascii"), _sha(data)

    def seed_test_configurations(self, account_id, configurations):
        """One-time explicit fixture assignment, before any commands/revisions.

        This owns its test data only; it cannot issue real tankmen or install
        unowned equipment in a live profile. Native inventory grants are absent.
        """
        _id(account_id, "account_id")
        if type(configurations) is not dict or not 1 <= len(configurations) <= MAX_OWNED:
            raise TransactionError("INVALID_INPUT")
        for vehicle_id, raw in configurations.items():
            _id(vehicle_id, "vehicle_id")
            if type(raw) is not bytes or not 0 < len(raw) <= crew.MAX_BYTES:
                raise TransactionError("INVALID_INPUT", "configuration bytes")
        connection = self.connection
        connection.execute("BEGIN IMMEDIATE")
        try:
            profile = self.read_profile(account_id)
            if profile["revision"] != 0 or profile["configurations"] or self.ledger_count(account_id):
                raise TransactionError("ALREADY_SEEDED_OR_USED")
            if set(configurations) != {v["vehicle_id"] for v in profile["vehicles"]}:
                raise TransactionError("UNKNOWN_VEHICLE")
            for vehicle_id, raw in sorted(configurations.items()):
                try:
                    encoded = raw.decode("ascii")
                except UnicodeError as error:
                    raise TransactionError("INVALID_INPUT", "ASCII configuration required") from error
                row = {"configuration_revision": 1, "configuration_json": encoded,
                       "configuration_sha256": _sha(raw)}
                ammo = next((a for a in profile["ammunition"] if a["vehicle_id"] == vehicle_id), None)
                self._configuration(account_id, vehicle_id, row, ammo)
                connection.execute("INSERT INTO crew_vehicle_configuration VALUES (?, ?, 1, ?, ?)",
                                   (account_id, vehicle_id, encoded, row["configuration_sha256"]))
            self._save_snapshot(account_id, 0)  # Includes cross-vehicle crew uniqueness.
            self._failpoint("before_configuration_seed_commit")
            connection.commit()
        except Exception:
            connection.rollback()
            raise

    def reserve_vehicle(self, *args, **kwargs):
        raise TransactionError("FULL_CONFIGURATION_RESERVATION_REQUIRED")

    def _frozen(self, profile, vehicle_id):
        config = next((c for c in profile["configurations"] if c["vehicle_id"] == vehicle_id), None)
        if config is None:
            raise TransactionError("MISSING_CONFIGURATION")
        ammo = next((a for a in profile["ammunition"] if a["vehicle_id"] == vehicle_id), None)
        if ammo is None or sum(ammo["loaded"].values()) == 0:
            raise TransactionError("NO_LOADED_AMMUNITION")
        row = self.connection.execute("SELECT * FROM crew_vehicle_configuration WHERE account_id=? AND vehicle_id=?",
                                      (profile["account_id"], vehicle_id)).fetchone()
        snapshot = self._configuration(profile["account_id"], vehicle_id, row, ammo)
        return {"format": "reserved-vehicle-configuration.v1", "crew_equipment": snapshot.as_dict(),
                "crew_equipment_sha256": snapshot.sha256, "ammunition": ammo,
                "ammo_catalog_sha256": CATALOG_SHA256,
                "equipment_ownership": "ISOLATED_FIXTURE_ONLY", "runtime_acceptance": "NOT_RUN"}

    def reserve_configuration(self, *, authenticated_account_id, account_id, command_id,
                              vehicle_id, expected_revision, expected_configuration_sha256, battle_id):
        _id(authenticated_account_id, "authenticated_account_id")
        _id(account_id, "account_id")
        if authenticated_account_id != account_id:
            raise TransactionError("FOREIGN_ACCOUNT")
        for label, value in (("command_id", command_id), ("vehicle_id", vehicle_id), ("battle_id", battle_id)):
            _id(value, label)
        _revision(expected_revision)
        _digest(expected_configuration_sha256)
        payload = {"schema": SCHEMA, "command": COMMAND, "account_id": account_id, "vehicle_id": vehicle_id,
                   "expected_revision": expected_revision, "battle_id": battle_id,
                   "expected_configuration_sha256": expected_configuration_sha256}
        payload_sha = _sha(_canonical(payload))
        connection = self.connection
        connection.execute("BEGIN IMMEDIATE")
        try:
            profile = self.read_profile(account_id)
            ledger = connection.execute("SELECT * FROM game_command_ledger WHERE account_id=? AND command_id=?",
                                        (account_id, command_id)).fetchone()
            if ledger is not None:
                if ledger["command_type"] != COMMAND or ledger["payload_sha256"] != payload_sha:
                    raise TransactionError("DUPLICATE_PAYLOAD_MISMATCH")
                result = self._configuration_replay(ledger, payload, command_id, profile)
                connection.commit()
                return result
            if expected_revision != profile["revision"]:
                raise TransactionError("STALE_REVISION")
            if expected_revision == 2**31 - 1:
                raise TransactionError("REVISION_EXHAUSTED")
            vehicle = next((v for v in profile["vehicles"] if v["vehicle_id"] == vehicle_id), None)
            if vehicle is None:
                raise TransactionError("UNKNOWN_VEHICLE")
            if vehicle["state"] != "available":
                raise TransactionError("VEHICLE_RESERVED")
            frozen = self._frozen(profile, vehicle_id)
            if frozen["crew_equipment"]["configuration_sha256"] != expected_configuration_sha256:
                raise TransactionError("STALE_CONFIGURATION")
            self._failpoint("after_configuration_read")
            connection.execute("UPDATE game_vehicle SET state='reserved', battle_id=? WHERE account_id=? AND vehicle_id=?",
                               (battle_id, account_id, vehicle_id))
            self._failpoint("after_vehicle_update")
            self._save_snapshot(account_id, expected_revision + 1)
            self._failpoint("after_snapshot_update")
            result = {"schema": SCHEMA, "command": COMMAND, "status": "reserved", "account_id": account_id,
                      "vehicle_id": vehicle_id, "battle_id": battle_id, "command_id": command_id,
                      "source_revision": expected_revision, "destination_revision": expected_revision + 1,
                      "frozen": frozen, "frozen_sha256": _sha(_canonical(frozen)), "replayed": False}
            raw = _canonical(result)
            connection.execute("INSERT INTO game_command_ledger(account_id, command_id, command_type, payload_sha256, "
                "source_revision, destination_revision, result_json, p09c_result_sha256) VALUES (?,?,?,?,?,?,?,?)",
                (account_id, command_id, COMMAND, payload_sha, expected_revision, expected_revision + 1,
                 raw.decode("ascii"), _sha(raw)))
            self._failpoint("after_ledger_insert")
            self._failpoint("before_commit")
            connection.commit()
            return result
        except Exception:
            connection.rollback()
            raise

    def _configuration_replay(self, row, payload, command_id, profile):
        result = _object(row["result_json"])
        keys = {"schema", "command", "status", "account_id", "vehicle_id", "battle_id", "command_id",
                "source_revision", "destination_revision", "frozen", "frozen_sha256", "replayed"}
        if set(result) != keys or _sha(_canonical(result)) != row["p09c_result_sha256"]:
            raise TransactionError("CORRUPT_STORE", "configuration ledger shape/digest")
        for key in ("schema", "command", "account_id", "vehicle_id", "battle_id"):
            if result[key] != payload[key]:
                raise TransactionError("CORRUPT_STORE", "configuration replay binding")
        source, destination = result["source_revision"], result["destination_revision"]
        _revision(source)
        _revision(destination)
        vehicle = next((v for v in profile["vehicles"] if v["vehicle_id"] == payload["vehicle_id"]), None)
        if (result["command_id"] != command_id or result["status"] != "reserved" or result["replayed"] is not False
                or source != payload["expected_revision"] or source != row["source_revision"]
                or destination != row["destination_revision"] or destination != source + 1
                or destination > profile["revision"] or vehicle is None or vehicle["state"] != "reserved"
                or vehicle["battle_id"] != payload["battle_id"]):
            raise TransactionError("CORRUPT_STORE", "configuration ledger invariant")
        frozen = self._frozen(profile, payload["vehicle_id"])
        if (frozen["crew_equipment"]["configuration_sha256"] != payload["expected_configuration_sha256"]
                or _canonical(result["frozen"]) != _canonical(frozen)
                or result["frozen_sha256"] != _sha(_canonical(frozen))):
            raise TransactionError("CORRUPT_STORE", "frozen configuration changed")
        return {**result, "replayed": True}

    def read_reserved_configuration(self, *, authenticated_account_id, account_id,
                                    command_id, battle_id, expected_frozen_sha256):
        """Return immutable canonical bytes for the exact authenticated battle.

        Do not consume an arbitrary caller-supplied snapshot/dict as proof of
        reservation. This read checks the persisted result and current locked
        vehicle under one SQLite read view, without incrementing any revision.
        """
        for label, value in (("authenticated_account_id", authenticated_account_id),
                             ("account_id", account_id), ("command_id", command_id), ("battle_id", battle_id)):
            _id(value, label)
        if authenticated_account_id != account_id:
            raise TransactionError("FOREIGN_ACCOUNT")
        _digest(expected_frozen_sha256)
        connection = self.connection
        connection.execute("BEGIN")
        try:
            profile = self.read_profile(account_id)
            row = connection.execute("SELECT * FROM game_command_ledger WHERE account_id=? AND command_id=?",
                                     (account_id, command_id)).fetchone()
            if row is None or row["command_type"] != COMMAND:
                raise TransactionError("UNKNOWN_RESERVATION")
            result = _object(row["result_json"])
            if result.get("battle_id") != battle_id or result.get("frozen_sha256") != expected_frozen_sha256:
                raise TransactionError("RESERVATION_BINDING_MISMATCH")
            # Derive the command only from persisted, integrity-checked server
            # state, and cross-check against the independent ledger payload pin.
            config = next((c for c in profile["configurations"] if c["vehicle_id"] == result.get("vehicle_id")), None)
            if config is None:
                raise TransactionError("CORRUPT_STORE", "reservation configuration missing")
            payload = {"schema": SCHEMA, "command": COMMAND, "account_id": account_id,
                       "vehicle_id": config["vehicle_id"], "expected_revision": row["source_revision"],
                       "battle_id": battle_id, "expected_configuration_sha256": config["configuration_sha256"]}
            if _sha(_canonical(payload)) != row["payload_sha256"]:
                raise TransactionError("CORRUPT_STORE", "reservation payload binding")
            verified = self._configuration_replay(row, payload, command_id, profile)
            raw = _canonical(verified["frozen"])
            connection.commit()
            return raw
        except Exception:
            connection.rollback()
            raise
