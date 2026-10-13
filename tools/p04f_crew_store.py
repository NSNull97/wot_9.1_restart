"""Versioned CMD105 assignments on the same authoritative crew/ammo writer."""
from __future__ import annotations

import argparse
from copy import deepcopy
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from server.domain.crew_transfer import Assignment, AssignmentError, transfer_assignments

from game_profile_tx import TransactionError, _bounded_id, _revision
from p09c_ammo_service import AmmoServiceStore, _object
from p09d_ammo_store import NativeAmmoStore, REQUEST_FIELDS, MAX_REQUEST, require, sha
from p04d_crew_store import NativeCrewStore, COMMAND as OLD_RECRUIT_COMMAND, audit_original as audit_crew_original
from p04d_crew_projection import POLICY_SHA256 as OLD_POLICY, SCHEMA as OLD_SCHEMA, SHOP_REVISION
from p04f_crew_projection import CrewTransferProjectionSource, SCHEMA, POLICY_SHA256, canonical, native_crew, update_delta, vehicle_crews

COMMAND = "p04f.crew_transfer.v1"
RECRUIT_COMMAND = "p04f.recruit_assign.v1"


def audit_original(original_root):
    from p04f_crew_source_audit import audit_sources
    return audit_sources(original_root)


def plan_assignment(inventory, layout, *, recruit=False, account_id=None):
    """Pure checked transition used both for live writes and durable replay validation."""
    native_crew(inventory)
    value = deepcopy(inventory)
    members = value["members"]
    require(value["configuration_revision"] < 2**31 - 1, "REVISION_EXHAUSTED")
    if recruit:
        require(layout == [SHOP_REVISION, 1, 1, 0], "RECRUIT_SELECTION_UNSUPPORTED")
        require(value["free_recruitment_left"] == 1, "FREE_RECRUITMENT_EXHAUSTED")
        require(type(account_id) is str, "FOREIGN_ACCOUNT")
        for row in members:
            if row["vehicle_native_id"] == 1 and row["seat"] == 1:
                row.update(vehicle_native_id=-1, seat=None)
        driver = members[1]
        members.append({"native_id": 3, "crew_id": account_id + ":recruit-ms1-driver:3", "role": "driver",
            "descriptor_hex": driver["descriptor_hex"], "vehicle_native_id": 1, "seat": 1})
        value.update(free_recruitment_left=0, next_native_id=4)
    else:
        vehicle, slot, tankman = layout
        require(vehicle == 1, "UNKNOWN_VEHICLE")
        require(slot in (-1, 0, 1) and (slot != -1 or tankman == -1), "TRANSFER_SELECTION_UNSUPPORTED")
        require(tankman == -1 or 1 <= tankman <= len(members), "UNKNOWN_TANKMAN")
        target = None if tankman == -1 else members[tankman - 1]
        if target is not None:
            require(target["role"] == ("commander" if slot == 0 else "driver"), "INCOMPATIBLE_CREW_ROLE")
        records = tuple(Assignment(row["native_id"], row["role"], row["vehicle_native_id"], row["seat"]) for row in members)
        try:
            assigned = transfer_assignments(records, vehicle, (frozenset({"commander"}), frozenset({"driver"})), slot, tankman, 16)
        except AssignmentError as error:
            raise TransactionError(error.code) from error
        for row, assignment in zip(members, assigned):
            row.update(vehicle_native_id=assignment.vehicle_id, seat=assignment.seat)
    require(sum(r["vehicle_native_id"] == -1 for r in members) <= 16, "BARRACKS_FULL")
    value["configuration_revision"] += 1
    native_crew(value)
    return value


class NativeCrewTransferStore(NativeCrewStore):
    SCHEMA, POLICY_SHA256 = SCHEMA, POLICY_SHA256
    COMMAND, RECRUIT_COMMAND = COMMAND, RECRUIT_COMMAND
    PROFILE_VERSION, CREW_VEHICLES = 7, (1,)
    SOURCE = CrewTransferProjectionSource
    native_crew = staticmethod(native_crew)
    project_crew = staticmethod(vehicle_crews)
    plan_assignment = staticmethod(plan_assignment)
    update_delta = staticmethod(update_delta)
    COMMAND_RESULT_BOUND = 8192

    @staticmethod
    def validate_recruit_layout(layout):
        require(layout[1:] == [1, 1, 0], "RECRUIT_SELECTION_UNSUPPORTED")

    @staticmethod
    def recruit_identity(account_id, native_id):
        return account_id + ":recruit-ms1-driver:" + str(native_id)

    @staticmethod
    def member_role_level(row):
        return 100

    @staticmethod
    def member_skills(row):
        return []

    @classmethod
    def operation_command(cls, operation):
        require(operation in ("recruit", "transfer"), "UNSUPPORTED_CREW_OPERATION")
        return cls.RECRUIT_COMMAND if operation == "recruit" else cls.COMMAND

    @classmethod
    def validate_operation_layout(cls, layout, operation):
        cls.operation_command(operation)
        require(type(layout) is list and len(layout) == (4 if operation == "recruit" else 3)
            and all(type(v) is int and -2**31 <= v < 2**31 for v in layout))
        if operation == "recruit":
            require(layout[0] == SHOP_REVISION, "SHOP_REVISION_MISMATCH")
            cls.validate_recruit_layout(layout)

    @classmethod
    def plan_operation(cls, before, layout, *, operation, account_id):
        return cls.plan_assignment(before, layout, recruit=operation == "recruit", account_id=account_id)

    @classmethod
    def operation_vehicles(cls, before, layout, *, operation):
        return cls.affected_vehicles(before, layout, recruit=operation == "recruit")

    @classmethod
    def operation_response(cls, request, revision, crew, *, operation, before_crew):
        return cls._response(request, revision, crew, recruit=operation == "recruit", before_crew=before_crew)

    def _operation_replay(self, ledger, request, profile, *, operation, command, payload_sha):
        return self._replay_existing(ledger, request, profile, recruit=operation == "recruit", command=command, payload_sha=payload_sha)

    def _historical_member_matches(self, historical, current):
        return all(historical[key] == current[key] for key in ("native_id", "crew_id", "role", "descriptor_hex"))

    def __init__(self, path, *, failpoint=None):
        super().__init__(path, failpoint=failpoint)
        self._allow_pretransfer = False

    def _contract(self):
        """Frozen behavior selected by the concrete versioned writer."""
        return type(self)

    def _transfer_schema(self):
        return self.connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='p04f_schema'").fetchone() is not None

    def initialize(self):
        if not self._transfer_schema():
            require(self._allow_pretransfer, "P04F_MIGRATION_REQUIRED")
            return NativeCrewStore.initialize(self)
        NativeAmmoStore.initialize(self)
        contract = self._contract()
        require([r[0] for r in self.connection.execute("SELECT version FROM p04f_schema")] == [contract.SCHEMA]
            and [r[0] for r in self.connection.execute("SELECT version FROM p04d_schema")] == [contract.SCHEMA], "UNSUPPORTED_STORE_SCHEMA")
        names = {r[0] for r in self.connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        require({"p04f_crew_meta", "p04d_crew_meta", "p04d_crew_member"} <= names, "CORRUPT_STORE")

    def migrate(self, *args, **kwargs):
        raise TransactionError("P04F_REQUIRES_ACCEPTED_PROFILE6")

    def migrate_crew(self, *args, **kwargs):
        raise TransactionError("P04F_REQUIRES_ACCEPTED_PROFILE6")

    def _crew_projection(self, account_id):
        if not self._transfer_schema():
            return NativeCrewStore._crew_projection(self, account_id)
        contract = self._contract()
        meta = self.connection.execute("SELECT * FROM p04d_crew_meta WHERE account_id=?", (account_id,)).fetchone()
        require(meta is not None and meta["policy_sha256"] == contract.POLICY_SHA256, "CORRUPT_STORE")
        rows = self.connection.execute("SELECT native_id,crew_id,role,descriptor_hex,vehicle_native_id,seat "
            "FROM p04d_crew_member WHERE account_id=? ORDER BY native_id LIMIT 17", (account_id,)).fetchall()
        value = {"policy_sha256": contract.POLICY_SHA256, "free_recruitment_left": meta["free_left"],
            "next_native_id": meta["next_native_id"], "configuration_revision": meta["configuration_revision"],
            "members": [dict(row) for row in rows]}
        try:
            contract.native_crew(value)
        except (ValueError, TypeError, KeyError) as error:
            raise TransactionError("CORRUPT_STORE", str(error)) from error
        imported = self._import(account_id)
        require(meta["source_bundle_sha256"] == imported["bundle_sha256"], "CORRUPT_STORE")
        original = _object(imported["base_json"])["crew"]
        require([r["crew_id"] for r in value["members"][:2]] == [r["crew_id"] for r in original], "CORRUPT_STORE")
        for row in value["members"][2:]:
            require(row["crew_id"] == contract.recruit_identity(account_id, row["native_id"]), "CORRUPT_STORE")
        return value

    def _snapshot(self, account_id, revision, vehicles):
        if not self._transfer_schema():
            return NativeCrewStore._snapshot(self, account_id, revision, vehicles)
        raw, _ = NativeAmmoStore._snapshot(self, account_id, revision, vehicles)
        value = _object(raw)
        value.update(crew_schema=self._contract().SCHEMA, crew_inventory=self._crew_projection(account_id))
        old = self.connection.execute("SELECT source_audit_sha256 FROM p04d_crew_meta WHERE account_id=?", (account_id,)).fetchone()
        new = self.connection.execute("SELECT source_audit_sha256,source_bundle_sha256,base_revision,base_profile_sha256 "
            "FROM p04f_crew_meta WHERE account_id=?", (account_id,)).fetchone()
        for row in (old, new):
            require(row is not None and type(row[0]) is str and re.fullmatch(r"[0-9a-f]{64}", row[0]) is not None, "CORRUPT_STORE")
        require(new[1] == self._import(account_id)["bundle_sha256"] and type(new[2]) is int
            and 6 <= new[2] < revision and type(new[3]) is str and re.fullmatch(r"[0-9a-f]{64}", new[3]) is not None, "CORRUPT_STORE")
        value.update(crew_source_audit_sha256=old[0], crew_transfer_source_audit_sha256=new[0])
        encoded = canonical(value)
        require(len(encoded) <= 16384, "PROFILE_TOO_LARGE")
        return encoded.decode("ascii"), sha(encoded)

    def _project_profile(self, account_id, aggregate):
        if not self._transfer_schema():
            return NativeCrewStore._project_profile(self, account_id, aggregate)
        value = NativeAmmoStore._project_profile(self, account_id, aggregate)
        current = aggregate["crew_inventory"]
        contract = self._contract()
        _, seats = contract.project_crew(current)
        vehicle_ids = {native: value["inventory"][native - 1]["inventory_id"] for native in contract.CREW_VEHICLES}
        value.update(profile_version=contract.PROFILE_VERSION,
            crew=[{"crew_id": row["crew_id"], "vehicle_inventory_id": vehicle_ids.get(row["vehicle_native_id"]),
                "role": row["role"], "role_level": contract.member_role_level(row), "skills": contract.member_skills(row)} for row in current["members"]],
            crew_service={"schema": contract.SCHEMA, "policy_sha256": contract.POLICY_SHA256,
                "free_recruitment_left": current["free_recruitment_left"],
                "configuration_revision": current["configuration_revision"], "battle": False})
        for native in contract.CREW_VEHICLES:
            value["inventory"][native - 1]["crew_assigned"] = all(seat is not None for seat in seats[native])
        require(len(canonical(value)) <= 8192, "PROFILE_TOO_LARGE")
        return value

    def migrate_transfer(self, source, *, account_id, original_root):
        require(isinstance(source, CrewTransferProjectionSource), "VERIFIED_SOURCE_REQUIRED")
        require(source.profile["account_id"] == account_id, "FOREIGN_ACCOUNT")
        audit_sha = sha(canonical(audit_original(original_root)))
        old_audit_sha = sha(canonical(audit_crew_original(original_root)))
        c = self.connection
        c.execute("BEGIN IMMEDIATE")
        self._allow_pretransfer = True
        try:
            self.initialize()
            old_meta = c.execute("SELECT source_audit_sha256 FROM p04d_crew_meta WHERE account_id=?", (account_id,)).fetchone()
            require(old_meta is not None and old_meta[0] == old_audit_sha, "MIGRATION_SOURCE_CHANGED")
            if self._transfer_schema():
                meta = c.execute("SELECT * FROM p04f_crew_meta WHERE account_id=?", (account_id,)).fetchone()
                require(meta is not None and meta["source_bundle_sha256"] == source.bundle_sha256
                    and meta["source_audit_sha256"] == audit_sha, "MIGRATION_SOURCE_CHANGED")
                profile = self.read_profile(account_id)
                c.commit()
                return {"status": "already_migrated", "account_id": account_id, "revision": profile["revision"]}
            base = self.read_profile(account_id)
            require(base["revision"] < 2**31 - 1, "REVISION_EXHAUSTED")
            require(all(row["state"] == "available" for row in base["vehicles"]), "VEHICLE_RESERVED")
            require(self._import(account_id)["bundle_sha256"] == source.bundle_sha256, "MIGRATION_SOURCE_CHANGED")
            before = c.execute("SELECT profile_json FROM game_profiles WHERE account_id=?", (account_id,)).fetchone()[0]
            require(_object(before)["profile_version"] == 6, "P04F_REQUIRES_ACCEPTED_PROFILE6")
            c.execute("CREATE TABLE p04f_schema(version TEXT PRIMARY KEY)")
            c.execute("CREATE TABLE p04f_crew_meta(account_id TEXT PRIMARY KEY REFERENCES game_snapshot(account_id),"
                "source_bundle_sha256 TEXT NOT NULL,source_audit_sha256 TEXT NOT NULL,base_revision INTEGER NOT NULL,base_profile_sha256 TEXT NOT NULL)")
            c.execute("INSERT INTO p04f_schema VALUES (?)", (SCHEMA,))
            c.execute("INSERT INTO p04f_crew_meta VALUES (?,?,?,?,?)", (account_id, source.bundle_sha256, audit_sha, base["revision"], sha(before.encode("ascii"))))
            require(c.execute("UPDATE p04d_schema SET version=? WHERE version=?", (SCHEMA, OLD_SCHEMA)).rowcount == 1, "UNSUPPORTED_STORE_SCHEMA")
            require(c.execute("UPDATE p04d_crew_meta SET policy_sha256=? WHERE account_id=? AND policy_sha256=?",
                (POLICY_SHA256, account_id, OLD_POLICY)).rowcount == 1, "MIGRATION_SOURCE_CHANGED")
            self._save_crew_projection(account_id, base["revision"] + 1, before)
            self._failpoint("before_transfer_migration_commit")
            self.read_profile(account_id)
            c.commit()
            return {"status": "migrated", "account_id": account_id, "revision": base["revision"] + 1,
                "policy_sha256": POLICY_SHA256, "retained_tankmen": len(base["crew_inventory"]["members"]), "new_tankmen": 0}
        except Exception:
            c.rollback()
            raise
        finally:
            self._allow_pretransfer = False

    def _save_crew_projection(self, account, revision, before):
        AmmoServiceStore._save_snapshot(self, account, revision)
        self._failpoint("after_snapshot_update")
        aggregate = _object(self.connection.execute("SELECT snapshot_json FROM game_snapshot WHERE account_id=?", (account,)).fetchone()[0])
        projected = canonical(self._project_profile(account, aggregate)).decode("ascii")
        require(self.connection.execute("UPDATE game_profiles SET profile_json=? WHERE account_id=? AND profile_json=?",
            (projected, account, before)).rowcount == 1, "STALE_PROFILE")
        self._failpoint("after_profile_projection")

    def publish(self, source, account_id, fixture_root):
        require(isinstance(source, self._contract().SOURCE), "CREW_TRANSFER_PROJECTION_REQUIRED")
        self.initialize()
        return NativeAmmoStore.publish(self, source, account_id, fixture_root)

    def transfer(self, request, *, authenticated_account_id):
        return self._mutate(request, authenticated_account_id, recruit=False)

    def recruit(self, request, *, authenticated_account_id):
        return self._mutate(request, authenticated_account_id, recruit=True)

    @staticmethod
    def affected_vehicles(before, layout, *, recruit):
        return (1,)

    def _replay_existing(self, ledger, request, profile, *, recruit, command, payload_sha):
        if recruit and ledger["command_type"] == OLD_RECRUIT_COMMAND:
            old_sha = sha(canonical({"schema": OLD_SCHEMA, "policy_sha256": OLD_POLICY,
                "command": OLD_RECRUIT_COMMAND, "request": request}))
            require(ledger["payload_sha256"] == old_sha, "DUPLICATE_PAYLOAD_MISMATCH")
            legacy = deepcopy(profile)
            inv = legacy["crew_inventory"]
            require(3 <= len(inv["members"]) <= 16, "CORRUPT_STORE")
            inv["members"] = inv["members"][:3]
            inv.update(policy_sha256=OLD_POLICY, configuration_revision=2, free_recruitment_left=0, next_native_id=4)
            for row in inv["members"]:
                row.update(vehicle_native_id=-1 if row["native_id"] == 2 else 1,
                    seat=None if row["native_id"] == 2 else (0 if row["native_id"] == 1 else 1))
            return NativeCrewStore._recruit_replay(self, ledger, request, legacy)
        require(ledger["command_type"] == command and ledger["payload_sha256"] == payload_sha, "DUPLICATE_PAYLOAD_MISMATCH")
        return self._transfer_replay(ledger, request, profile, recruit=recruit)

    def _mutate(self, request, authenticated_account_id, *, recruit=False, operation=None):
        self.initialize()
        contract = self._contract()
        operation = ("recruit" if recruit else "transfer") if operation is None else operation
        require(type(request) is dict and set(request) == REQUEST_FIELDS)
        _bounded_id(authenticated_account_id, "authenticated_account_id")
        _bounded_id(request["account_id"], "account_id")
        require(request["account_id"] == authenticated_account_id, "FOREIGN_ACCOUNT")
        _bounded_id(request["command_key"], "command_key")
        _revision(request["expected_revision"])
        require(type(request["native_database_id"]) is int and 1 <= request["native_database_id"] < 2**31)
        require(type(request["wire_revision"]) is int and 1 <= request["wire_revision"] < 2**31 - 1)
        layout = request["layout"]
        contract.validate_operation_layout(layout, operation)
        request_bytes = canonical(request)
        require(len(request_bytes) <= MAX_REQUEST)
        request = _object(request_bytes.decode("ascii"))
        account, key = request["account_id"], request["command_key"]
        command = contract.operation_command(operation)
        payload_sha = sha(canonical({"schema": contract.SCHEMA, "policy_sha256": contract.POLICY_SHA256, "command": command, "request": request}))
        c = self.connection
        c.execute("BEGIN IMMEDIATE")
        try:
            profile = self.read_profile(account)
            stored_raw = c.execute("SELECT profile_json FROM game_profiles WHERE account_id=?", (account,)).fetchone()[0]
            stored = _object(stored_raw)
            require(stored["native_database_id"] == request["native_database_id"], "FOREIGN_ACCOUNT")
            ledger = c.execute("SELECT * FROM game_command_ledger WHERE account_id=? AND command_id=?", (account, key)).fetchone()
            if ledger is not None:
                result = self._operation_replay(ledger, request, profile, operation=operation, command=command, payload_sha=payload_sha)
                c.commit()
                return result
            revision = profile["revision"]
            require(revision == request["expected_revision"], "STALE_REVISION")
            require(revision < 2**31 - 1, "REVISION_EXHAUSTED")
            before = profile["crew_inventory"]
            for native in contract.operation_vehicles(before, request["layout"], operation=operation):
                vehicle_id = stored["inventory"][native - 1]["inventory_id"]
                vehicle = next((r for r in profile["vehicles"] if r["vehicle_id"] == vehicle_id), None)
                require(vehicle is not None and vehicle["state"] == "available", "VEHICLE_RESERVED")
            after = contract.plan_operation(before, request["layout"], operation=operation, account_id=account)
            # Vacate first, then assign: the unique-seat index is never bypassed.
            for row in before["members"]:
                changed = after["members"][row["native_id"] - 1]
                if (row["vehicle_native_id"], row["seat"]) != (changed["vehicle_native_id"], changed["seat"]):
                    c.execute("UPDATE p04d_crew_member SET vehicle_native_id=-1,seat=NULL WHERE account_id=? AND native_id=?", (account, row["native_id"]))
            self._failpoint("after_transfer_unassign")
            for row in after["members"]:
                if row["native_id"] > len(before["members"]):
                    c.execute("INSERT INTO p04d_crew_member VALUES (?,?,?,?,?,?,?)", (account, row["native_id"], row["crew_id"], row["role"], row["descriptor_hex"], row["vehicle_native_id"], row["seat"]))
                else:
                    c.execute("UPDATE p04d_crew_member SET vehicle_native_id=?,seat=?,descriptor_hex=? WHERE account_id=? AND native_id=?",
                        (row["vehicle_native_id"], row["seat"], row["descriptor_hex"], account, row["native_id"]))
            self._failpoint("after_transfer_assign")
            require(c.execute("UPDATE p04d_crew_meta SET next_native_id=?,free_left=?,configuration_revision=? WHERE account_id=? AND configuration_revision=?",
                (after["next_native_id"], after["free_recruitment_left"], after["configuration_revision"], account, before["configuration_revision"])).rowcount == 1, "STALE_CREW")
            self._failpoint("after_transfer_meta_update")
            self._save_crew_projection(account, revision + 1, stored_raw)
            response = contract.operation_response(request, revision + 1, after, operation=operation, before_crew=before)
            result = {"schema": contract.SCHEMA, "command": command, "source_revision": revision,
                "destination_revision": revision + 1, "before_crew": before, "after_crew": after, "response": response}
            raw, reply = canonical(result), canonical(response)
            require(len(raw) <= contract.COMMAND_RESULT_BOUND, "PROFILE_TOO_LARGE")
            c.execute("INSERT INTO game_command_ledger VALUES (?,?,?,?,?,?,?,?)", (account, key, command, payload_sha,
                revision, revision + 1, raw.decode("ascii"), sha(raw)))
            c.execute("INSERT INTO p09d_native_command VALUES (?,?,?,?,?)", (account, key, sha(request_bytes), reply.decode("ascii"), sha(reply)))
            self._failpoint("after_transfer_ledger_insert")
            self.read_profile(account)
            self._failpoint("before_commit")
            c.commit()
            return response
        except Exception:
            c.rollback()
            raise

    @classmethod
    def _response(cls, request, revision, crew, *, recruit, before_crew=None):
        return dict(status="recruited" if recruit else "transferred", account_id=request["account_id"],
            native_database_id=request["native_database_id"], command_key=request["command_key"], revision=revision,
            wire_revision=request["wire_revision"] + 1,
            update_hex=cls.update_delta(crew, request["wire_revision"], recruit=recruit).hex(), replayed=False, result_code=0)

    def _transfer_replay(self, row, request, profile, *, recruit, contract=None):
        return self._replay_mutation(row, request, profile, operation="recruit" if recruit else "transfer", contract=contract)

    def _replay_mutation(self, row, request, profile, *, operation, contract=None):
        contract = self._contract() if contract is None else contract
        result = _object(row["result_json"])
        require(sha(canonical(result)) == row["p09c_result_sha256"] and set(result) == {"schema", "command",
            "source_revision", "destination_revision", "before_crew", "after_crew", "response"}, "CORRUPT_STORE")
        source, destination = result["source_revision"], result["destination_revision"]
        require(result["schema"] == contract.SCHEMA and result["command"] == contract.operation_command(operation)
            and type(source) is int and type(destination) is int and source == request["expected_revision"]
            and source == row["source_revision"] and destination == row["destination_revision"]
            and destination == source + 1 and destination <= profile["revision"], "CORRUPT_STORE")
        try:
            after = contract.plan_operation(result["before_crew"], request["layout"], operation=operation, account_id=request["account_id"])
            require(after == result["after_crew"], "CORRUPT_STORE")
            current = profile["crew_inventory"]
            for member in after["members"]:
                actual = current["members"][member["native_id"] - 1]
                require(self._historical_member_matches(member, actual), "CORRUPT_STORE")
            require(after["configuration_revision"] <= current["configuration_revision"], "CORRUPT_STORE")
        except (ValueError, KeyError, TypeError, IndexError) as error:
            raise TransactionError("CORRUPT_STORE", str(error)) from error
        expected = contract.operation_response(request, destination, after, operation=operation, before_crew=result["before_crew"])
        native = self.connection.execute("SELECT * FROM p09d_native_command WHERE account_id=? AND command_id=?", (request["account_id"], request["command_key"])).fetchone()
        require(native is not None and native["request_sha256"] == sha(canonical(request))
            and native["response_json"] == canonical(expected).decode("ascii") and native["response_sha256"] == sha(canonical(expected))
            and canonical(result["response"]) == canonical(expected), "CORRUPT_STORE")
        return {**expected, "replayed": True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("database", "bundle", "original-root", "account-id", "fixture-root"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("operation", choices=("activate", "fixture", "service", "recruit", "transfer"))
    args = parser.parse_args()
    audit_original(args.original_root)
    with NativeCrewTransferStore(args.database) as store:
        if args.operation == "activate":
            source = CrewTransferProjectionSource(args.bundle)
            result = store.migrate_transfer(source, account_id=args.account_id, original_root=args.original_root)
            result.update(store.publish(source, args.account_id, args.fixture_root))
        elif args.operation == "fixture":
            result = store.publish(CrewTransferProjectionSource(args.bundle), args.account_id, args.fixture_root)
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
