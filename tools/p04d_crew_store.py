"""One authoritative game.sqlite writer for P09D ammo and narrow CMD309 crew.

The one free 100% driver and fixed passport are explicit project test policy.
Migration preserves the two existing tankmen; only recruit creates a third.
"""
from __future__ import annotations

import argparse
import re
import sys

from game_profile_tx import TransactionError, _bounded_id, _revision
from p09c_ammo_service import AmmoServiceStore, _object
from p09d_ammo_store import NativeAmmoStore, REQUEST_FIELDS, MAX_REQUEST, require, sha
from p04d_crew_projection import (
    CrewProjectionSource, SCHEMA, POLICY_SHA256, canonical, native_crew, update_delta, SHOP_REVISION,
)

COMMAND = "p04d.recruit_assign.v1"
DDL = (
    "CREATE TABLE p04d_schema(version TEXT PRIMARY KEY)",
    """CREATE TABLE p04d_crew_meta(account_id TEXT PRIMARY KEY REFERENCES game_snapshot(account_id),
       next_native_id INTEGER NOT NULL CHECK(next_native_id BETWEEN 3 AND 2147483647),
       free_left INTEGER NOT NULL CHECK(free_left IN (0,1)),
       configuration_revision INTEGER NOT NULL CHECK(configuration_revision BETWEEN 1 AND 2147483647),
       source_bundle_sha256 TEXT NOT NULL,source_audit_sha256 TEXT NOT NULL,policy_sha256 TEXT NOT NULL)""",
    """CREATE TABLE p04d_crew_member(account_id TEXT NOT NULL REFERENCES game_snapshot(account_id),
       native_id INTEGER NOT NULL CHECK(native_id BETWEEN 1 AND 2147483647),
       crew_id TEXT NOT NULL,role TEXT NOT NULL CHECK(role IN ('commander','driver')),descriptor_hex TEXT NOT NULL,
       vehicle_native_id INTEGER NOT NULL CHECK(vehicle_native_id IN (-1,1)),seat INTEGER,
       PRIMARY KEY(account_id,native_id),UNIQUE(account_id,crew_id),
       CHECK((vehicle_native_id=-1 AND seat IS NULL) OR (vehicle_native_id=1 AND seat IN (0,1))))""",
    "CREATE UNIQUE INDEX p04d_crew_seat ON p04d_crew_member(account_id,vehicle_native_id,seat) WHERE vehicle_native_id>=0",
)


def audit_original(original_root):
    # Imported only once the separately owned source auditor is available.
    from p04d_crew_source_audit import audit_sources
    return audit_sources(original_root)


class NativeCrewStore(NativeAmmoStore):
    def __init__(self, path, *, failpoint=None):
        super().__init__(path, failpoint=failpoint)
        self._allow_precrew = False

    def _crew_schema(self):
        return self.connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='p04d_schema'").fetchone() is not None

    def initialize(self):
        super().initialize()
        if self._allow_precrew and not self._crew_schema():
            return
        require(self._crew_schema(), "P04D_MIGRATION_REQUIRED")
        require([r[0] for r in self.connection.execute("SELECT version FROM p04d_schema")] == [SCHEMA], "UNSUPPORTED_STORE_SCHEMA")
        names = {r[0] for r in self.connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        require({"p04d_crew_meta", "p04d_crew_member"} <= names, "CORRUPT_STORE")

    def migrate(self, source, **arguments):
        """Allow the already-versioned P09D migration before the crew extension."""
        self._allow_precrew = True
        try:
            return super().migrate(source, **arguments)
        finally:
            self._allow_precrew = False

    def _crew_projection(self, account_id):
        meta = self.connection.execute("SELECT * FROM p04d_crew_meta WHERE account_id=?", (account_id,)).fetchone()
        require(meta is not None and meta["policy_sha256"] == POLICY_SHA256, "CORRUPT_STORE")
        rows = self.connection.execute("SELECT native_id,crew_id,role,descriptor_hex,vehicle_native_id,seat "
            "FROM p04d_crew_member WHERE account_id=? ORDER BY native_id LIMIT 17", (account_id,)).fetchall()
        value = {"policy_sha256": meta["policy_sha256"], "free_recruitment_left": meta["free_left"],
                 "next_native_id": meta["next_native_id"], "configuration_revision": meta["configuration_revision"],
                 "members": [dict(row) for row in rows]}
        try:
            native_crew(value)
        except (ValueError, TypeError, KeyError) as error:
            raise TransactionError("CORRUPT_STORE", str(error)) from error
        imported = self._import(account_id)
        require(meta["source_bundle_sha256"] == imported["bundle_sha256"], "CORRUPT_STORE")
        original = _object(imported["base_json"])["crew"]
        require([r["crew_id"] for r in value["members"][:2]] == [r["crew_id"] for r in original], "CORRUPT_STORE")
        for row in value["members"][2:]:
            require(row["crew_id"] == account_id + ":recruit-ms1-driver:" + str(row["native_id"]), "CORRUPT_STORE")
        return value

    def _snapshot(self, account_id, revision, vehicles):
        raw, checksum = super()._snapshot(account_id, revision, vehicles)
        if not self._crew_schema():
            return raw, checksum
        value = _object(raw)
        value["crew_schema"] = SCHEMA
        value["crew_inventory"] = self._crew_projection(account_id)
        audit_sha = self.connection.execute("SELECT source_audit_sha256 FROM p04d_crew_meta WHERE account_id=?",
                                            (account_id,)).fetchone()[0]
        require(type(audit_sha) is str and re.fullmatch(r"[0-9a-f]{64}", audit_sha) is not None, "CORRUPT_STORE")
        value["crew_source_audit_sha256"] = audit_sha
        encoded = canonical(value)
        require(len(encoded) <= 16384, "PROFILE_TOO_LARGE")
        return encoded.decode("ascii"), sha(encoded)

    def _project_profile(self, account_id, aggregate):
        value = super()._project_profile(account_id, aggregate)
        if not self._crew_schema():
            return value
        current = aggregate["crew_inventory"]
        vehicle_id = value["inventory"][0]["inventory_id"]
        value.update(profile_version=6,
            crew=[{"crew_id": row["crew_id"],
                   "vehicle_inventory_id": vehicle_id if row["vehicle_native_id"] == 1 else None,
                   "role": row["role"], "role_level": 100, "skills": []} for row in current["members"]],
            crew_service={"schema": SCHEMA, "policy_sha256": POLICY_SHA256,
                "free_recruitment_left": current["free_recruitment_left"],
                "configuration_revision": current["configuration_revision"], "battle": False})
        value["inventory"][0]["crew_assigned"] = True
        require(len(canonical(value)) <= 8192, "PROFILE_TOO_LARGE")
        return value

    def migrate_crew(self, source, *, account_id, original_root):
        require(isinstance(source, CrewProjectionSource), "VERIFIED_SOURCE_REQUIRED")
        require(source.profile["account_id"] == account_id, "FOREIGN_ACCOUNT")
        receipt = audit_original(original_root)
        audit_sha = sha(canonical(receipt))
        c = self.connection
        c.execute("BEGIN IMMEDIATE")
        try:
            NativeAmmoStore.initialize(self)
            if self._crew_schema():
                self.initialize()
                meta = c.execute("SELECT * FROM p04d_crew_meta WHERE account_id=?", (account_id,)).fetchone()
                require(meta is not None and meta["source_bundle_sha256"] == source.bundle_sha256
                        and meta["source_audit_sha256"] == audit_sha, "MIGRATION_SOURCE_CHANGED")
                profile = self.read_profile(account_id)
                c.commit()
                return {"status": "already_migrated", "account_id": account_id, "revision": profile["revision"]}
            base = self.read_profile(account_id)
            require(base["revision"] < 2**31 - 1, "REVISION_EXHAUSTED")
            imported = self._import(account_id)
            require(imported["bundle_sha256"] == source.bundle_sha256, "MIGRATION_SOURCE_CHANGED")
            require(all(row["state"] == "available" for row in base["vehicles"]), "VEHICLE_RESERVED")
            before = c.execute("SELECT profile_json FROM game_profiles WHERE account_id=?", (account_id,)).fetchone()[0]
            for sql in DDL:
                c.execute(sql)
            c.execute("INSERT INTO p04d_schema VALUES (?)", (SCHEMA,))
            c.execute("INSERT INTO p04d_crew_meta VALUES (?,3,1,1,?,?,?)",
                      (account_id, source.bundle_sha256, audit_sha, POLICY_SHA256))
            for index, row in enumerate(source.profile["crew"], 1):
                role = "commander" if index == 1 else "driver"
                require(row["role"] == role and row["role_level"] == 100 and row["skills"] == [], "MIGRATION_SOURCE_CHANGED")
                c.execute("INSERT INTO p04d_crew_member VALUES (?,?,?,?,?,1,?)",
                          (account_id, index, row["crew_id"], role, source.descriptors[role], index - 1))
            AmmoServiceStore._save_snapshot(self, account_id, base["revision"] + 1)
            aggregate = _object(c.execute("SELECT snapshot_json FROM game_snapshot WHERE account_id=?", (account_id,)).fetchone()[0])
            projected = canonical(self._project_profile(account_id, aggregate)).decode("ascii")
            require(c.execute("UPDATE game_profiles SET profile_json=? WHERE account_id=? AND profile_json=?",
                              (projected, account_id, before)).rowcount == 1, "STALE_PROFILE")
            self._failpoint("before_crew_migration_commit")
            self.read_profile(account_id)
            c.commit()
            return {"status": "migrated", "account_id": account_id, "revision": base["revision"] + 1,
                    "policy_sha256": POLICY_SHA256, "retained_tankmen": 2, "new_tankmen": 0}
        except Exception:
            c.rollback()
            raise

    def service(self, request, *, authenticated_account_id):
        self.initialize()
        return super().service(request, authenticated_account_id=authenticated_account_id)

    def publish(self, source, account_id, fixture_root):
        require(isinstance(source, CrewProjectionSource), "CREW_PROJECTION_REQUIRED")
        self.initialize()
        return super().publish(source, account_id, fixture_root)

    def recruit(self, request, *, authenticated_account_id):
        self.initialize()
        require(type(request) is dict and set(request) == REQUEST_FIELDS)
        _bounded_id(authenticated_account_id, "authenticated_account_id")
        _bounded_id(request["account_id"], "account_id")
        require(request["account_id"] == authenticated_account_id, "FOREIGN_ACCOUNT")
        _bounded_id(request["command_key"], "command_key")
        _revision(request["expected_revision"])
        require(type(request["native_database_id"]) is int and 1 <= request["native_database_id"] < 2**31)
        require(type(request["wire_revision"]) is int and 1 <= request["wire_revision"] < 2**31 - 1)
        layout = request["layout"]
        require(type(layout) is list and len(layout) == 4 and all(type(v) is int for v in layout))
        require(layout[0] == SHOP_REVISION, "SHOP_REVISION_MISMATCH")
        require(layout[1:] == [1, 1, 0], "RECRUIT_SELECTION_UNSUPPORTED")
        request_bytes = canonical(request)
        require(len(request_bytes) <= MAX_REQUEST)
        # A caller-owned mutable dict must not change after its payload pin.
        request = _object(request_bytes.decode("ascii"))
        account, key = request["account_id"], request["command_key"]
        payload = {"schema": SCHEMA, "policy_sha256": POLICY_SHA256, "command": COMMAND, "request": request}
        payload_sha = sha(canonical(payload))
        c = self.connection
        c.execute("BEGIN IMMEDIATE")
        try:
            profile = self.read_profile(account)
            stored = _object(c.execute("SELECT profile_json FROM game_profiles WHERE account_id=?", (account,)).fetchone()[0])
            require(stored["native_database_id"] == request["native_database_id"], "FOREIGN_ACCOUNT")
            ledger = c.execute("SELECT * FROM game_command_ledger WHERE account_id=? AND command_id=?", (account, key)).fetchone()
            if ledger is not None:
                require(ledger["command_type"] == COMMAND and ledger["payload_sha256"] == payload_sha, "DUPLICATE_PAYLOAD_MISMATCH")
                result = self._recruit_replay(ledger, request, profile)
                c.commit()
                return result
            revision = profile["revision"]
            require(revision == request["expected_revision"], "STALE_REVISION")
            require(revision < 2**31 - 1, "REVISION_EXHAUSTED")
            vehicle_id = stored["inventory"][0]["inventory_id"]
            vehicle = next((row for row in profile["vehicles"] if row["vehicle_id"] == vehicle_id), None)
            require(vehicle is not None and vehicle["state"] == "available", "VEHICLE_RESERVED")
            inventory = profile["crew_inventory"]
            require(inventory["free_recruitment_left"] == 1, "FREE_RECRUITMENT_EXHAUSTED")
            require(len(inventory["members"]) < 16
                    and sum(r["vehicle_native_id"] == -1 for r in inventory["members"]) < 16, "BARRACKS_FULL")
            next_id = inventory["next_native_id"]
            require(next_id == 3, "UNSUPPORTED_CREW_STATE")
            driver = next(r for r in inventory["members"] if r["vehicle_native_id"] == 1 and r["seat"] == 1)
            before = c.execute("SELECT profile_json FROM game_profiles WHERE account_id=?", (account,)).fetchone()[0]
            require(c.execute("UPDATE p04d_crew_member SET vehicle_native_id=-1,seat=NULL "
                "WHERE account_id=? AND native_id=? AND vehicle_native_id=1 AND seat=1", (account, driver["native_id"])).rowcount == 1, "STALE_CREW")
            self._failpoint("after_old_driver_unassigned")
            crew_id = account + ":recruit-ms1-driver:" + str(next_id)
            c.execute("INSERT INTO p04d_crew_member VALUES (?,?,?,?,?,1,1)",
                      (account, next_id, crew_id, "driver", driver["descriptor_hex"]))
            self._failpoint("after_tankman_insert")
            require(c.execute("UPDATE p04d_crew_meta SET next_native_id=next_native_id+1,free_left=0,"
                "configuration_revision=configuration_revision+1 WHERE account_id=? AND free_left=1 AND next_native_id=?",
                (account, next_id)).rowcount == 1, "STALE_CREW")
            self._failpoint("after_crew_quota_update")
            AmmoServiceStore._save_snapshot(self, account, revision + 1)
            self._failpoint("after_snapshot_update")
            aggregate = _object(c.execute("SELECT snapshot_json FROM game_snapshot WHERE account_id=?", (account,)).fetchone()[0])
            projected = canonical(self._project_profile(account, aggregate)).decode("ascii")
            require(c.execute("UPDATE game_profiles SET profile_json=? WHERE account_id=? AND profile_json=?",
                              (projected, account, before)).rowcount == 1, "STALE_PROFILE")
            self._failpoint("after_profile_projection")
            update = update_delta(aggregate["crew_inventory"], request["wire_revision"])
            response = dict(status="recruited", account_id=account, native_database_id=request["native_database_id"],
                command_key=key, revision=revision + 1, wire_revision=request["wire_revision"] + 1,
                update_hex=update.hex(), replayed=False, result_code=0)
            result = {"schema": SCHEMA, "command": COMMAND, "source_revision": revision,
                      "destination_revision": revision + 1, "crew_id": crew_id, "native_inventory_id": next_id,
                      "displaced_native_inventory_id": driver["native_id"], "response": response}
            result_raw, response_raw = canonical(result), canonical(response)
            c.execute("INSERT INTO game_command_ledger(account_id,command_id,command_type,payload_sha256,source_revision,"
                "destination_revision,result_json,p09c_result_sha256) VALUES (?,?,?,?,?,?,?,?)",
                (account, key, COMMAND, payload_sha, revision, revision + 1, result_raw.decode("ascii"), sha(result_raw)))
            c.execute("INSERT INTO p09d_native_command VALUES (?,?,?,?,?)",
                      (account, key, sha(canonical(request)), response_raw.decode("ascii"), sha(response_raw)))
            self._failpoint("after_crew_ledger_insert")
            self.read_profile(account)
            self._failpoint("before_commit")
            c.commit()
            return response
        except Exception:
            c.rollback()
            raise

    def _recruit_replay(self, row, request, profile):
        result = _object(row["result_json"])
        require(sha(canonical(result)) == row["p09c_result_sha256"], "CORRUPT_STORE")
        expected_keys = {"schema", "command", "source_revision", "destination_revision", "crew_id",
                         "native_inventory_id", "displaced_native_inventory_id", "response"}
        require(set(result) == expected_keys and result["schema"] == SCHEMA and result["command"] == COMMAND, "CORRUPT_STORE")
        source, destination = result["source_revision"], result["destination_revision"]
        require(type(source) is int and type(destination) is int and source == request["expected_revision"]
                and source == row["source_revision"] and destination == row["destination_revision"]
                and destination == source + 1 and destination <= profile["revision"], "CORRUPT_STORE")
        inventory = profile["crew_inventory"]
        require(result["native_inventory_id"] == 3 and type(result["native_inventory_id"]) is int
                and result["displaced_native_inventory_id"] == 2 and type(result["displaced_native_inventory_id"]) is int
                and result["crew_id"] == request["account_id"] + ":recruit-ms1-driver:3"
                and inventory["free_recruitment_left"] == 0, "CORRUPT_STORE")
        expected = dict(status="recruited", account_id=request["account_id"], native_database_id=request["native_database_id"],
            command_key=request["command_key"], revision=destination, wire_revision=request["wire_revision"] + 1,
            update_hex=update_delta(inventory, request["wire_revision"]).hex(), replayed=False, result_code=0)
        native = self.connection.execute("SELECT * FROM p09d_native_command WHERE account_id=? AND command_id=?",
                                        (request["account_id"], request["command_key"])).fetchone()
        require(native is not None and native["request_sha256"] == sha(canonical(request))
                and native["response_sha256"] == sha(canonical(expected))
                and native["response_json"] == canonical(expected).decode("ascii")
                and canonical(result["response"]) == canonical(expected), "CORRUPT_STORE")
        return {**expected, "replayed": True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("database", "bundle", "original-root", "account-id", "fixture-root"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("operation", choices=("activate", "fixture", "service", "recruit"))
    args = parser.parse_args()
    audit_original(args.original_root)
    with NativeCrewStore(args.database) as store:
        if args.operation == "activate":
            source = CrewProjectionSource(args.bundle)
            store.migrate(source, account_id=args.account_id, original_root=args.original_root,
                          grant={"grant_id": "p09d-test-depot-v1", "quantity_each": 100})
            result = store.migrate_crew(source, account_id=args.account_id, original_root=args.original_root)
            result.update(store.publish(source, args.account_id, args.fixture_root))
        elif args.operation == "fixture":
            store.initialize()
            result = store.publish(CrewProjectionSource(args.bundle), args.account_id, args.fixture_root)
        else:
            store.initialize()
            raw = sys.stdin.buffer.read(MAX_REQUEST + 1)
            require(len(raw) <= MAX_REQUEST)
            request = _object(raw.decode("ascii"))
            method = store.recruit if args.operation == "recruit" else store.service
            try:
                result = method(request, authenticated_account_id=args.account_id)
            except TransactionError:
                revision = store.read_profile(args.account_id)["revision"]
                result = dict(status="rejected", account_id=args.account_id,
                    native_database_id=request.get("native_database_id"), command_key=request.get("command_key"),
                    revision=revision, wire_revision=request.get("wire_revision"), update_hex="", replayed=False, result_code=-10)
        print(canonical(result).decode("ascii"))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(type(error).__name__ + ": " + str(error), file=sys.stderr)
        raise SystemExit(1)
