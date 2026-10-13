"""Versioned roster recruitment on the inherited sole crew/ammunition writer."""
from __future__ import annotations

import argparse
from copy import deepcopy
from pathlib import Path
import sys

from p04f_crew_store import (NativeCrewTransferStore, Assignment, AssignmentError,
    transfer_assignments, TransactionError, require, canonical, sha, _object, MAX_REQUEST,
    audit_original as audit_transfer_original, audit_crew_original)
from p04g_crew_store import NativeCrossVehicleCrewStore, audit_original as audit_cross_original
from p04h_crew_projection import (RosterRecruitmentProjectionSource, SCHEMA, POLICY_SHA256,
    SEAT_ROLES, ROLE_LEVEL, CAPACITY, native_crew, update_delta)
from p04h_tankman_descriptor import decode_descriptor, recruit_descriptor, verify_catalog

COMMAND = "p04h.crew_transfer.v1"
RECRUIT_COMMAND = "p04h.recruit_assign.v1"
SOURCE_AUDIT_SHA256 = "db7179a139d7caabd92aa1026f20e163c5a8583267bb0a1aa95541d248abf585"


def audit_original(original_root):
    from p04h_crew_source_audit import audit_sources
    result = audit_sources(Path(original_root))
    require(sha(canonical(result)) == SOURCE_AUDIT_SHA256, "MIGRATION_SOURCE_CHANGED")
    verify_catalog(original_root)
    return result


def validate_recruit_layout(layout):
    require(layout[1] in SEAT_ROLES and 0 <= layout[2] < len(SEAT_ROLES[layout[1]]) and layout[3] == 0,
            "RECRUIT_SELECTION_UNSUPPORTED")


def recruit_identity(account_id, native_id):
    return account_id + (":recruit-ms1-driver:" if native_id == 3 else ":recruit-crew:") + str(native_id)


def plan_assignment(inventory, layout, *, recruit=False, account_id=None):
    native_crew(inventory)
    value = deepcopy(inventory)
    require(value["configuration_revision"] < 2**31 - 1, "REVISION_EXHAUSTED")
    members = value["members"]
    if recruit:
        require(layout[0] == 3, "SHOP_REVISION_MISMATCH")
        validate_recruit_layout(layout)
        _, vehicle, slot, _ = layout
        require(value["free_recruitment_left"] > 0 and len(members) < CAPACITY, "FREE_RECRUITMENT_EXHAUSTED")
        require(type(account_id) is str, "FOREIGN_ACCOUNT")
        native_id = value["next_native_id"]
        for member in members:
            if member["vehicle_native_id"] == vehicle and member["seat"] == slot:
                member.update(vehicle_native_id=-1, seat=None)
        role = SEAT_ROLES[vehicle][slot]
        raw = recruit_descriptor(native_id, {1: 13, 2: 28}[vehicle], role, ROLE_LEVEL)
        members.append(dict(native_id=native_id, crew_id=recruit_identity(account_id, native_id),
            role=role, descriptor_hex=raw.hex(), vehicle_native_id=vehicle, seat=slot))
        value.update(next_native_id=native_id + 1, free_recruitment_left=CAPACITY - len(members))
    else:
        vehicle, slot, tankman = layout
        require(vehicle in SEAT_ROLES, "UNKNOWN_VEHICLE")
        require(-1 <= slot < len(SEAT_ROLES[vehicle]) and (slot != -1 or tankman == -1), "TRANSFER_SELECTION_UNSUPPORTED")
        require(tankman == -1 or 1 <= tankman <= len(members), "UNKNOWN_TANKMAN")
        records = tuple(Assignment(row["native_id"], row["role"], row["vehicle_native_id"], row["seat"]) for row in members)
        try:
            assigned = transfer_assignments(records, vehicle, tuple(frozenset({role}) for role in SEAT_ROLES[vehicle]), slot, tankman, CAPACITY)
        except AssignmentError as error:
            raise TransactionError(error.code) from error
        for row, assignment in zip(members, assigned):
            row.update(vehicle_native_id=assignment.vehicle_id, seat=assignment.seat)
    value["configuration_revision"] += 1
    native_crew(value)
    return value


class NativeRosterRecruitmentStore(NativeCrossVehicleCrewStore):
    SCHEMA, POLICY_SHA256 = SCHEMA, POLICY_SHA256
    COMMAND, RECRUIT_COMMAND = COMMAND, RECRUIT_COMMAND
    PROFILE_VERSION, CREW_VEHICLES = 9, (1, 2)
    SOURCE = RosterRecruitmentProjectionSource
    COMMAND_RESULT_BOUND = 16384
    native_crew = staticmethod(native_crew)
    project_crew = staticmethod(native_crew)
    update_delta = staticmethod(update_delta)
    plan_assignment = staticmethod(plan_assignment)
    validate_recruit_layout = staticmethod(validate_recruit_layout)
    recruit_identity = staticmethod(recruit_identity)

    def __init__(self, path, *, failpoint=None):
        super().__init__(path, failpoint=failpoint)
        self._allow_preroster = False

    def _roster_schema(self):
        return self.connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='p04h_schema'").fetchone() is not None

    def _contract(self):
        if self._allow_preroster and not self._roster_schema():
            return NativeCrossVehicleCrewStore
        return type(self)

    def initialize(self):
        if not self._roster_schema():
            require(self._allow_preroster, "P04H_MIGRATION_REQUIRED")
            return super().initialize()
        NativeCrewTransferStore.initialize(self)
        for table in ("p04g_schema", "p04h_schema"):
            require([r[0] for r in self.connection.execute("SELECT version FROM " + table)] == [SCHEMA], "UNSUPPORTED_STORE_SCHEMA")
        require(self.connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='p04h_crew_meta'").fetchone() is not None, "CORRUPT_STORE")

    def migrate_cross(self, *args, **kwargs):
        raise TransactionError("P04H_REQUIRES_ACCEPTED_PROFILE8")

    @staticmethod
    def member_role_level(row):
        return decode_descriptor(bytes.fromhex(row["descriptor_hex"]))["role_level"]

    def _snapshot(self, account_id, revision, vehicles):
        raw, digest = super()._snapshot(account_id, revision, vehicles)
        if not self._roster_schema():
            return raw, digest
        meta = self.connection.execute("SELECT * FROM p04h_crew_meta WHERE account_id=?", (account_id,)).fetchone()
        require(meta is not None and meta["source_audit_sha256"] == SOURCE_AUDIT_SHA256
            and meta["source_bundle_sha256"] == self._import(account_id)["bundle_sha256"]
            and type(meta["base_revision"]) is int and 8 <= meta["base_revision"] < revision
            and sha(meta["base_profile_json"].encode("ascii")) == meta["base_profile_sha256"], "CORRUPT_STORE")
        predecessor = _object(meta["base_profile_json"])
        require(predecessor.get("account_id") == account_id and predecessor.get("profile_version") == 8
            and predecessor.get("snapshot_revision") == meta["base_revision"]
            and predecessor.get("crew_service", {}).get("schema") == NativeCrossVehicleCrewStore.SCHEMA
            and predecessor["crew_service"].get("policy_sha256") == NativeCrossVehicleCrewStore.POLICY_SHA256
            and predecessor["crew_service"].get("free_recruitment_left") == 0
            and len(predecessor.get("crew", [])) == 3, "CORRUPT_STORE")
        value = _object(raw)
        value["crew_roster_source_audit_sha256"] = meta["source_audit_sha256"]
        encoded = canonical(value)
        require(len(encoded) <= 16384, "PROFILE_TOO_LARGE")
        return encoded.decode("ascii"), sha(encoded)

    def migrate_roster(self, source, *, account_id, original_root):
        require(isinstance(source, RosterRecruitmentProjectionSource), "VERIFIED_SOURCE_REQUIRED")
        require(source.profile["account_id"] == account_id, "FOREIGN_ACCOUNT")
        audit_sha = sha(canonical(audit_original(original_root)))
        cross_sha = sha(canonical(audit_cross_original(original_root)))
        prior_audits = (("p04d_crew_meta", sha(canonical(audit_crew_original(Path(original_root))))),
                        ("p04f_crew_meta", sha(canonical(audit_transfer_original(Path(original_root))))))
        c = self.connection
        c.execute("BEGIN IMMEDIATE")
        self._allow_preroster = True
        try:
            self.initialize()
            for table, digest in prior_audits:
                rows = c.execute("SELECT account_id,source_bundle_sha256,source_audit_sha256 FROM " + table).fetchall()
                require(len(rows) == 1 and tuple(rows[0]) == (account_id, source.bundle_sha256, digest), "MIGRATION_SOURCE_CHANGED")
            prior = c.execute("SELECT * FROM p04g_crew_meta WHERE account_id=?", (account_id,)).fetchone()
            require(prior is not None and prior["source_audit_sha256"] == cross_sha
                and prior["source_bundle_sha256"] == source.bundle_sha256
                and self._import(account_id)["bundle_sha256"] == source.bundle_sha256, "MIGRATION_SOURCE_CHANGED")
            base = self.read_profile(account_id)
            if self._roster_schema():
                c.commit()
                return {"status": "already_migrated", "account_id": account_id, "revision": base["revision"]}
            require(base["revision"] < 2**31 - 1, "REVISION_EXHAUSTED")
            require(all(row["state"] == "available" for row in base["vehicles"]), "VEHICLE_RESERVED")
            before = c.execute("SELECT profile_json FROM game_profiles WHERE account_id=?", (account_id,)).fetchone()[0]
            require(_object(before)["profile_version"] == 8 and len(base["crew_inventory"]["members"]) == 3
                and base["crew_inventory"]["free_recruitment_left"] == 0, "P04H_REQUIRES_ACCEPTED_PROFILE8")
            c.execute("CREATE TABLE p04h_schema(version TEXT PRIMARY KEY)")
            c.execute("CREATE TABLE p04h_crew_meta(account_id TEXT PRIMARY KEY REFERENCES game_snapshot(account_id),"
                "source_bundle_sha256 TEXT NOT NULL,source_audit_sha256 TEXT NOT NULL,base_revision INTEGER NOT NULL,"
                "base_profile_sha256 TEXT NOT NULL,base_profile_json TEXT NOT NULL)")
            c.execute("INSERT INTO p04h_schema VALUES (?)", (SCHEMA,))
            c.execute("INSERT INTO p04h_crew_meta VALUES (?,?,?,?,?,?)", (account_id, source.bundle_sha256, audit_sha, base["revision"], sha(before.encode("ascii")), before))
            # Both old CHECK constraints change; rebuild transactionally, retaining
            # each row and all source/audit fields in the sole authoritative tables.
            c.execute("DROP INDEX p04d_crew_seat")
            c.execute("ALTER TABLE p04d_crew_member RENAME TO p04h_old_member")
            c.execute("""CREATE TABLE p04d_crew_member(account_id TEXT NOT NULL REFERENCES game_snapshot(account_id),
                native_id INTEGER NOT NULL CHECK(native_id BETWEEN 1 AND 16),crew_id TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('commander','driver','gunner','loader')),descriptor_hex TEXT NOT NULL CHECK(length(descriptor_hex)=50),
                vehicle_native_id INTEGER NOT NULL CHECK(vehicle_native_id IN (-1,1,2)),seat INTEGER,
                PRIMARY KEY(account_id,native_id),UNIQUE(account_id,crew_id),
                CHECK((vehicle_native_id=-1 AND seat IS NULL) OR (seat IS NOT NULL AND
                  ((vehicle_native_id=1 AND ((role='commander' AND seat=0) OR (role='driver' AND seat=1))) OR
                   (vehicle_native_id=2 AND ((role='commander' AND seat=0) OR (role='gunner' AND seat=1) OR
                    (role='driver' AND seat=2) OR (role='loader' AND seat IN (3,4))))))))""")
            c.execute("INSERT INTO p04d_crew_member SELECT * FROM p04h_old_member")
            c.execute("DROP TABLE p04h_old_member")
            c.execute("CREATE UNIQUE INDEX p04d_crew_seat ON p04d_crew_member(account_id,vehicle_native_id,seat) WHERE vehicle_native_id>=0")
            c.execute("ALTER TABLE p04d_crew_meta RENAME TO p04h_old_meta")
            c.execute("""CREATE TABLE p04d_crew_meta(account_id TEXT PRIMARY KEY REFERENCES game_snapshot(account_id),
                next_native_id INTEGER NOT NULL CHECK(next_native_id BETWEEN 4 AND 17),
                free_left INTEGER NOT NULL CHECK(free_left BETWEEN 0 AND 13),
                configuration_revision INTEGER NOT NULL CHECK(configuration_revision BETWEEN 1 AND 2147483647),
                source_bundle_sha256 TEXT NOT NULL,source_audit_sha256 TEXT NOT NULL,policy_sha256 TEXT NOT NULL)""")
            c.execute("INSERT INTO p04d_crew_meta SELECT * FROM p04h_old_meta")
            c.execute("DROP TABLE p04h_old_meta")
            self._failpoint("after_roster_table_rebuild")
            for table in ("p04d_schema", "p04f_schema", "p04g_schema"):
                require(c.execute("UPDATE " + table + " SET version=? WHERE version=?", (SCHEMA, NativeCrossVehicleCrewStore.SCHEMA)).rowcount == 1, "UNSUPPORTED_STORE_SCHEMA")
            require(c.execute("UPDATE p04d_crew_meta SET policy_sha256=?,free_left=13 WHERE account_id=? AND policy_sha256=? AND free_left=0",
                (POLICY_SHA256, account_id, NativeCrossVehicleCrewStore.POLICY_SHA256)).rowcount == 1, "MIGRATION_SOURCE_CHANGED")
            self._save_crew_projection(account_id, base["revision"] + 1, before)
            self._failpoint("before_roster_migration_commit")
            self.read_profile(account_id)
            c.commit()
            return {"status": "migrated", "account_id": account_id, "revision": base["revision"] + 1,
                "policy_sha256": POLICY_SHA256, "retained_tankmen": 3, "new_tankmen": 0, "free_recruitment_left": 13}
        except Exception:
            c.rollback()
            raise
        finally:
            self._allow_preroster = False

    @staticmethod
    def affected_vehicles(before, layout, *, recruit):
        if recruit:
            return (layout[1],)
        return NativeCrossVehicleCrewStore.affected_vehicles(before, layout, recruit=False)

    @classmethod
    def _response(cls, request, revision, crew, *, recruit, before_crew=None):
        value = dict(status="recruited" if recruit else "transferred", account_id=request["account_id"],
            native_database_id=request["native_database_id"], command_key=request["command_key"], revision=revision,
            wire_revision=request["wire_revision"] + 1, replayed=False, result_code=0)
        value["update_hex"] = update_delta(crew, request["wire_revision"], recruit=recruit, before_crew=before_crew).hex()
        return value

    def _replay_existing(self, ledger, request, profile, *, recruit, command, payload_sha):
        old_command = NativeCrossVehicleCrewStore.RECRUIT_COMMAND if recruit else NativeCrossVehicleCrewStore.COMMAND
        if ledger["command_type"] == old_command:
            old_sha = sha(canonical({"schema": NativeCrossVehicleCrewStore.SCHEMA,
                "policy_sha256": NativeCrossVehicleCrewStore.POLICY_SHA256, "command": old_command, "request": request}))
            require(ledger["payload_sha256"] == old_sha, "DUPLICATE_PAYLOAD_MISMATCH")
            return self._transfer_replay(ledger, request, profile, recruit=recruit, contract=NativeCrossVehicleCrewStore)
        return super()._replay_existing(ledger, request, profile, recruit=recruit, command=command, payload_sha=payload_sha)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("database", "bundle", "original-root", "account-id", "fixture-root"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("operation", choices=("activate", "fixture", "service", "recruit", "transfer"))
    args = parser.parse_args()
    audit_original(args.original_root)
    with NativeRosterRecruitmentStore(args.database) as store:
        if args.operation == "activate":
            source = RosterRecruitmentProjectionSource(args.bundle)
            result = store.migrate_roster(source, account_id=args.account_id, original_root=args.original_root)
            result.update(store.publish(source, args.account_id, args.fixture_root))
        elif args.operation == "fixture":
            result = store.publish(RosterRecruitmentProjectionSource(args.bundle), args.account_id, args.fixture_root)
        else:
            store.initialize()
            raw = sys.stdin.buffer.read(MAX_REQUEST + 1)
            require(len(raw) <= MAX_REQUEST)
            request = _object(raw.decode("ascii"))
            method = {"service": store.service, "recruit": store.recruit, "transfer": store.transfer}[args.operation]
            try:
                result = method(request, authenticated_account_id=args.account_id)
            except TransactionError:
                result = dict(status="rejected", account_id=args.account_id, native_database_id=request.get("native_database_id"),
                    command_key=request.get("command_key"), revision=store.read_profile(args.account_id)["revision"],
                    wire_revision=request.get("wire_revision"), update_hex="", replayed=False, result_code=-10)
        print(canonical(result).decode("ascii"))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(type(error).__name__ + ": " + str(error), file=sys.stderr)
        raise SystemExit(1)
