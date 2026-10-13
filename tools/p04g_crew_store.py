"""Versioned two-vehicle crew policy on the existing authoritative writer."""
from __future__ import annotations

import argparse
from copy import deepcopy
from pathlib import Path
import re
import sys

from p04f_crew_store import (NativeCrewTransferStore, Assignment, AssignmentError,
    transfer_assignments, TransactionError, require, canonical, sha, _object, MAX_REQUEST,
    audit_original as audit_transfer_original, audit_crew_original)
from p04g_crew_projection import (CrossVehicleCrewProjectionSource, SCHEMA, POLICY_SHA256,
    SEAT_ROLES, native_crew, update_delta)

COMMAND = "p04g.crew_transfer.v1"
RECRUIT_COMMAND = "p04g.recruit_assign.v1"
SOURCE_AUDIT_SHA256 = "e0693e0e36d2b5ca0c72e584684439b3b1c6eecfa9709b06820cbbc8832c7cb9"


def audit_original(original_root):
    from p04g_crew_source_audit import audit_sources
    result = audit_sources(Path(original_root))
    require(sha(canonical(result)) == SOURCE_AUDIT_SHA256, "MIGRATION_SOURCE_CHANGED")
    return result


def plan_assignment(inventory, layout, *, recruit=False, account_id=None):
    """The source-bound adapter supplies roles; the generic planner moves records."""
    native_crew(inventory)
    require(not recruit, "FREE_RECRUITMENT_EXHAUSTED")
    value = deepcopy(inventory)
    require(value["configuration_revision"] < 2**31 - 1, "REVISION_EXHAUSTED")
    vehicle, slot, tankman = layout
    require(vehicle in SEAT_ROLES, "UNKNOWN_VEHICLE")
    require(-1 <= slot < len(SEAT_ROLES[vehicle]) and (slot != -1 or tankman == -1), "TRANSFER_SELECTION_UNSUPPORTED")
    require(tankman == -1 or 1 <= tankman <= len(value["members"]), "UNKNOWN_TANKMAN")
    records = tuple(Assignment(row["native_id"], row["role"], row["vehicle_native_id"], row["seat"])
                    for row in value["members"])
    try:
        assigned = transfer_assignments(records, vehicle,
            tuple(frozenset({role}) for role in SEAT_ROLES[vehicle]), slot, tankman, 16)
    except AssignmentError as error:
        raise TransactionError(error.code) from error
    for row, assignment in zip(value["members"], assigned):
        row.update(vehicle_native_id=assignment.vehicle_id, seat=assignment.seat)
    value["configuration_revision"] += 1
    native_crew(value)
    return value


class NativeCrossVehicleCrewStore(NativeCrewTransferStore):
    SCHEMA, POLICY_SHA256 = SCHEMA, POLICY_SHA256
    COMMAND, RECRUIT_COMMAND = COMMAND, RECRUIT_COMMAND
    PROFILE_VERSION, CREW_VEHICLES = 8, (1, 2)
    SOURCE = CrossVehicleCrewProjectionSource
    native_crew = staticmethod(native_crew)
    project_crew = staticmethod(native_crew)
    plan_assignment = staticmethod(plan_assignment)
    update_delta = staticmethod(update_delta)

    def __init__(self, path, *, failpoint=None):
        super().__init__(path, failpoint=failpoint)
        self._allow_precross = False

    def _cross_schema(self):
        return self.connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='p04g_schema'").fetchone() is not None

    def _contract(self):
        # The migration reads and verifies the original F snapshot before changing
        # any marker. Historical replay instead explicitly selects the frozen F
        # contract over the immutable journal's before/after snapshots.
        if self._allow_precross and not self._cross_schema():
            return NativeCrewTransferStore
        return type(self)

    def initialize(self):
        if not self._cross_schema():
            require(self._allow_precross, "P04G_MIGRATION_REQUIRED")
            return super().initialize()
        super().initialize()
        require([r[0] for r in self.connection.execute("SELECT version FROM p04g_schema")] == [SCHEMA], "UNSUPPORTED_STORE_SCHEMA")
        require(self.connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='p04g_crew_meta'").fetchone() is not None, "CORRUPT_STORE")

    def migrate_transfer(self, *args, **kwargs):
        raise TransactionError("P04G_REQUIRES_ACCEPTED_PROFILE7")

    def _snapshot(self, account_id, revision, vehicles):
        raw, digest = super()._snapshot(account_id, revision, vehicles)
        if not self._cross_schema():
            return raw, digest
        meta = self.connection.execute("SELECT * FROM p04g_crew_meta WHERE account_id=?", (account_id,)).fetchone()
        require(meta is not None and meta["source_audit_sha256"] == SOURCE_AUDIT_SHA256
            and meta["source_bundle_sha256"] == self._import(account_id)["bundle_sha256"]
            and type(meta["base_revision"]) is int and 7 <= meta["base_revision"] < revision
            and type(meta["base_profile_sha256"]) is str
            and re.fullmatch(r"[0-9a-f]{64}", meta["base_profile_sha256"]) is not None, "CORRUPT_STORE")
        value = _object(raw)
        value["crew_cross_source_audit_sha256"] = meta["source_audit_sha256"]
        encoded = canonical(value)
        require(len(encoded) <= 16384, "PROFILE_TOO_LARGE")
        return encoded.decode("ascii"), sha(encoded)

    def migrate_cross(self, source, *, account_id, original_root):
        require(isinstance(source, CrossVehicleCrewProjectionSource), "VERIFIED_SOURCE_REQUIRED")
        require(source.profile["account_id"] == account_id, "FOREIGN_ACCOUNT")
        audit_sha = sha(canonical(audit_original(original_root)))
        transfer_audit_sha = sha(canonical(audit_transfer_original(original_root)))
        crew_audit_sha = sha(canonical(audit_crew_original(original_root)))
        c = self.connection
        c.execute("BEGIN IMMEDIATE")
        self._allow_precross = True
        try:
            self.initialize()
            for table, digest in (("p04d_crew_meta", crew_audit_sha), ("p04f_crew_meta", transfer_audit_sha)):
                rows = c.execute("SELECT account_id,source_bundle_sha256,source_audit_sha256 FROM " + table).fetchall()
                require(len(rows) == 1 and tuple(rows[0]) == (account_id, source.bundle_sha256, digest), "MIGRATION_SOURCE_CHANGED")
            base = self.read_profile(account_id)
            if self._cross_schema():
                meta = c.execute("SELECT * FROM p04g_crew_meta WHERE account_id=?", (account_id,)).fetchone()
                require(meta["source_audit_sha256"] == audit_sha and meta["source_bundle_sha256"] == source.bundle_sha256, "MIGRATION_SOURCE_CHANGED")
                c.commit()
                return {"status": "already_migrated", "account_id": account_id, "revision": base["revision"]}
            require(base["revision"] < 2**31 - 1, "REVISION_EXHAUSTED")
            require(all(row["state"] == "available" for row in base["vehicles"]), "VEHICLE_RESERVED")
            require(self._import(account_id)["bundle_sha256"] == source.bundle_sha256, "MIGRATION_SOURCE_CHANGED")
            before = c.execute("SELECT profile_json FROM game_profiles WHERE account_id=?", (account_id,)).fetchone()[0]
            require(_object(before)["profile_version"] == 7 and len(base["crew_inventory"]["members"]) == 3
                and base["crew_inventory"]["free_recruitment_left"] == 0, "P04G_REQUIRES_ACCEPTED_PROFILE7")
            c.execute("CREATE TABLE p04g_schema(version TEXT PRIMARY KEY)")
            c.execute("CREATE TABLE p04g_crew_meta(account_id TEXT PRIMARY KEY REFERENCES game_snapshot(account_id),"
                "source_bundle_sha256 TEXT NOT NULL,source_audit_sha256 TEXT NOT NULL,base_revision INTEGER NOT NULL,base_profile_sha256 TEXT NOT NULL)")
            c.execute("INSERT INTO p04g_schema VALUES (?)", (SCHEMA,))
            c.execute("INSERT INTO p04g_crew_meta VALUES (?,?,?,?,?)", (account_id, source.bundle_sha256, audit_sha, base["revision"], sha(before.encode("ascii"))))
            # SQLite cannot alter a CHECK. Rebuild the sole existing crew table
            # transactionally and retain every identity and descriptor byte.
            c.execute("DROP INDEX p04d_crew_seat")
            c.execute("ALTER TABLE p04d_crew_member RENAME TO p04g_migration_old_member")
            c.execute("""CREATE TABLE p04d_crew_member(account_id TEXT NOT NULL REFERENCES game_snapshot(account_id),
                native_id INTEGER NOT NULL CHECK(native_id BETWEEN 1 AND 2147483647),
                crew_id TEXT NOT NULL,role TEXT NOT NULL CHECK(role IN ('commander','driver')),descriptor_hex TEXT NOT NULL,
                vehicle_native_id INTEGER NOT NULL CHECK(vehicle_native_id IN (-1,1,2)),seat INTEGER,
                PRIMARY KEY(account_id,native_id),UNIQUE(account_id,crew_id),
                CHECK((vehicle_native_id=-1 AND seat IS NULL) OR
                    (vehicle_native_id IN (1,2) AND seat IS NOT NULL AND
                     ((role='commander' AND seat=0) OR
                      (role='driver' AND ((vehicle_native_id=1 AND seat=1) OR (vehicle_native_id=2 AND seat=2)))))))""")
            c.execute("INSERT INTO p04d_crew_member SELECT * FROM p04g_migration_old_member")
            c.execute("DROP TABLE p04g_migration_old_member")
            c.execute("CREATE UNIQUE INDEX p04d_crew_seat ON p04d_crew_member(account_id,vehicle_native_id,seat) WHERE vehicle_native_id>=0")
            self._failpoint("after_cross_table_rebuild")
            for table in ("p04d_schema", "p04f_schema"):
                require(c.execute("UPDATE " + table + " SET version=? WHERE version=?", (SCHEMA, NativeCrewTransferStore.SCHEMA)).rowcount == 1, "UNSUPPORTED_STORE_SCHEMA")
            require(c.execute("UPDATE p04d_crew_meta SET policy_sha256=? WHERE account_id=? AND policy_sha256=?",
                (POLICY_SHA256, account_id, NativeCrewTransferStore.POLICY_SHA256)).rowcount == 1, "MIGRATION_SOURCE_CHANGED")
            self._save_crew_projection(account_id, base["revision"] + 1, before)
            self._failpoint("before_cross_migration_commit")
            self.read_profile(account_id)
            c.commit()
            return {"status": "migrated", "account_id": account_id, "revision": base["revision"] + 1,
                "policy_sha256": POLICY_SHA256, "retained_tankmen": 3, "new_tankmen": 0}
        except Exception:
            c.rollback()
            raise
        finally:
            self._allow_precross = False

    @staticmethod
    def affected_vehicles(before, layout, *, recruit):
        if recruit:
            return (1,)
        target, _, tankman = layout
        require(target in SEAT_ROLES, "UNKNOWN_VEHICLE")
        member = next((r for r in before["members"] if r["native_id"] == tankman), None)
        origin = -1 if member is None else member["vehicle_native_id"]
        return tuple(sorted({target, origin} - {-1}))

    def _replay_existing(self, ledger, request, profile, *, recruit, command, payload_sha):
        old_command = NativeCrewTransferStore.RECRUIT_COMMAND if recruit else NativeCrewTransferStore.COMMAND
        if ledger["command_type"] == old_command:
            old_sha = sha(canonical({"schema": NativeCrewTransferStore.SCHEMA,
                "policy_sha256": NativeCrewTransferStore.POLICY_SHA256, "command": old_command, "request": request}))
            require(ledger["payload_sha256"] == old_sha, "DUPLICATE_PAYLOAD_MISMATCH")
            return self._transfer_replay(ledger, request, profile, recruit=recruit, contract=NativeCrewTransferStore)
        return super()._replay_existing(ledger, request, profile, recruit=recruit, command=command, payload_sha=payload_sha)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("database", "bundle", "original-root", "account-id", "fixture-root"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("operation", choices=("activate", "fixture", "service", "recruit", "transfer"))
    args = parser.parse_args()
    audit_original(args.original_root)
    with NativeCrossVehicleCrewStore(args.database) as store:
        if args.operation == "activate":
            source = CrossVehicleCrewProjectionSource(args.bundle)
            result = store.migrate_cross(source, account_id=args.account_id, original_root=args.original_root)
            result.update(store.publish(source, args.account_id, args.fixture_root))
        elif args.operation == "fixture":
            result = store.publish(CrossVehicleCrewProjectionSource(args.bundle), args.account_id, args.fixture_root)
        else:
            store.initialize()
            raw = sys.stdin.buffer.read(MAX_REQUEST + 1)
            require(len(raw) <= MAX_REQUEST)
            request = _object(raw.decode("ascii"))
            method = {"service": store.service, "recruit": store.recruit, "transfer": store.transfer}[args.operation]
            try:
                result = method(request, authenticated_account_id=args.account_id)
            except TransactionError:
                result = dict(status="rejected", account_id=args.account_id,
                    native_database_id=request.get("native_database_id"), command_key=request.get("command_key"),
                    revision=store.read_profile(args.account_id)["revision"], wire_revision=request.get("wire_revision"),
                    update_hex="", replayed=False, result_code=-10)
        print(canonical(result).decode("ascii"))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(type(error).__name__ + ": " + str(error), file=sys.stderr)
        raise SystemExit(1)
