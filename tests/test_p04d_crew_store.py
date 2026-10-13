"""Same-game.sqlite native crew/ammo atomicity with real source activation."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import threading
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
try:
    from p04d_crew_store import NativeCrewStore, COMMAND
    from p04d_crew_projection import CrewProjectionSource, canonical, POLICY_SHA256, native_crew
    from p09d_ammo_store import NativeAmmoStore
    from p09d_ammo_projection import ProjectionSource
    from p09c_ammo_service import AmmoServiceStore
    from game_profile_tx import TransactionError
except ModuleNotFoundError as error:
    if error.name not in ("p09d_ammo_projection", "p09d_ammo_store"):
        raise
    NativeCrewStore = None

BUNDLE = Path(os.environ["P04D_TEST_BUNDLE"]) if os.environ.get("P04D_TEST_BUNDLE") else None
CONFIG = Path(os.environ.get("WOT091_CONFIG", ROOT / "config/project.local.json"))
TEMP = ROOT / "local/evidence/20261013-p04d-native-crew-recruitment-01/persistence-research/tmp"
GRANT = {"grant_id": "p09d-test-depot-v1", "quantity_each": 100}


class CrewStoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if NativeCrewStore is None or BUNDLE is None or not BUNDLE.is_dir() or not CONFIG.is_file():
            raise unittest.SkipTest("NOT_RUN: frozen P09D, P04D_TEST_BUNDLE and WOT091_CONFIG required")
        cls.original = Path(json.loads(CONFIG.read_text(encoding="utf-8-sig"))["paths"]["original_client_root"])
        cls.source = CrewProjectionSource(BUNDLE)
        cls.account = cls.source.profile["account_id"]
        cls.native_id = cls.source.profile["native_database_id"]

    def setUp(self):
        TEMP.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix="crew-", dir=TEMP)
        self.addCleanup(self.temp.cleanup)
        self.database = Path(self.temp.name) / "game.sqlite"
        with closing(sqlite3.connect(self.database)) as c:
            c.executescript("""PRAGMA user_version=1;
                CREATE TABLE game_meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
                CREATE TABLE game_profiles(native_id INTEGER PRIMARY KEY AUTOINCREMENT,account_id TEXT NOT NULL UNIQUE,profile_json TEXT NOT NULL);
                CREATE TABLE game_limits(key_hash TEXT PRIMARY KEY,hits INTEGER NOT NULL,resets_at INTEGER NOT NULL);""")
            c.execute("INSERT INTO game_profiles VALUES (?,?,?)",
                      (self.native_id, self.account, canonical(self.source.profile).decode("ascii")))
            c.execute("INSERT INTO game_profiles VALUES (999,?,?)", ("untouched-account", '{"unrelated":true}'))
            c.execute("INSERT INTO game_meta VALUES ('unrelated','preserve-me')")
            c.commit()
        self.store = NativeCrewStore(self.database)
        self.addCleanup(lambda: self.store.close())
        self.store.migrate(self.source, account_id=self.account, original_root=self.original, grant=GRANT)

    def activate(self):
        return self.store.migrate_crew(self.source, account_id=self.account, original_root=self.original)

    def request(self, **changes):
        value = dict(account_id=self.account, native_database_id=self.native_id, command_key="crew-session:request309",
                     expected_revision=6, wire_revision=1, layout=[3, 1, 1, 0])
        value.update(changes)
        return value

    def recruit(self, request=None):
        return self.store.recruit(request or self.request(), authenticated_account_id=self.account)

    def ammo_request(self, **changes):
        value = self.request(command_key="ammo-session:request108", layout=[3, 1, 6, 2570, 30, 2826, 10, 3082, 5, 6, 0, 0, 0, 0, 0, 0])
        value.update(changes)
        return value

    def ammo(self, **changes):
        return self.store.service(self.ammo_request(**changes), authenticated_account_id=self.account)

    def state(self):
        return list(self.store.connection.iterdump())

    def profile(self):
        return self.store.read_profile(self.account)

    def public(self):
        return json.loads(self.store.connection.execute("SELECT profile_json FROM game_profiles WHERE account_id=?", (self.account,)).fetchone()[0])

    def reopen(self):
        self.store.close(); self.store = NativeCrewStore(self.database); self.store.initialize()

    def reject(self, code, operation):
        before = self.state()
        with self.assertRaises(TransactionError) as raised:
            operation()
        self.assertEqual(raised.exception.code, code)
        self.assertEqual(self.state(), before)
        self.assertFalse(self.store.connection.in_transaction)

    def test_migration_retains_two_tankmen_and_assignments_without_fake_recruit(self):
        result = self.activate()
        self.assertEqual((result["revision"], result["retained_tankmen"], result["new_tankmen"]), (6, 2, 0))
        inventory = self.profile()["crew_inventory"]
        self.assertEqual((len(inventory["members"]), inventory["free_recruitment_left"], inventory["next_native_id"]), (2, 1, 3))
        self.assertEqual(self.public()["crew"], self.source.profile["crew"])
        self.assertEqual(self.public()["profile_version"], 6)
        self.assertEqual(self.store.ledger_count(self.account), 0)
        for key in ("resources", "statistics", "crew_grant", "test_grant", "ammo_grant"):
            self.assertEqual(self.public()[key], self.source.profile[key])
        self.assertEqual(self.store.connection.execute("SELECT profile_json FROM game_profiles WHERE native_id=999").fetchone()[0], '{"unrelated":true}')

    def test_service_and_recruit_require_explicit_crew_activation(self):
        self.reject("P04D_MIGRATION_REQUIRED", lambda: self.recruit())
        self.reject("P04D_MIGRATION_REQUIRED", lambda: self.ammo())

    def test_failed_source_activation_preserves_existing_game_database(self):
        before = self.state()
        empty_original = Path(self.temp.name) / "empty-original"
        empty_original.mkdir()
        with self.assertRaises(ValueError):
            self.store.migrate_crew(self.source, account_id=self.account, original_root=empty_original)
        self.assertEqual(self.state(), before)
        self.assertFalse(self.store.connection.in_transaction)

    def test_recruit_replaces_only_driver_preserves_displaced_man_and_all_balances(self):
        self.activate(); before = self.profile(); public = self.public()
        response = self.recruit()
        after = self.profile(); inventory = after["crew_inventory"]
        self.assertEqual(response["status"], "recruited")
        self.assertEqual((response["revision"], response["wire_revision"], response["result_code"]), (7, 2, 0))
        self.assertFalse(response["replayed"])
        self.assertEqual([r["vehicle_native_id"] for r in inventory["members"]], [1, -1, 1])
        self.assertEqual([r["seat"] for r in inventory["members"]], [0, None, 1])
        self.assertEqual((inventory["next_native_id"], inventory["free_recruitment_left"], inventory["configuration_revision"]), (4, 0, 2))
        self.assertEqual(inventory["members"][1]["descriptor_hex"], inventory["members"][2]["descriptor_hex"])
        self.assertNotEqual(inventory["members"][1]["crew_id"], inventory["members"][2]["crew_id"])
        self.assertEqual(self.public()["crew"][1]["vehicle_inventory_id"], None)
        self.assertEqual(self.public()["resources"], public["resources"])
        self.assertEqual(after["ammunition"], before["ammunition"])
        self.assertEqual(after["depot"], before["depot"])
        self.assertEqual(self.store.ledger_count(self.account), 1)

    def test_migration_repetition_never_restores_spent_quota_or_removes_new_driver(self):
        self.activate(); self.recruit(); before = self.state()
        self.assertEqual(self.store.migrate(self.source, account_id=self.account,
            original_root=self.original, grant=GRANT)["status"], "already_migrated")
        self.assertEqual(self.activate()["status"], "already_migrated")
        self.assertEqual(self.state(), before)

    def test_replay_after_reopen_and_later_ammo_returns_identical_response(self):
        self.activate(); original = self.recruit()
        self.ammo(expected_revision=7, wire_revision=2)
        self.reopen(); before = self.state()
        self.assertEqual(self.recruit(), {**original, "replayed": True})
        self.assertEqual(self.state(), before)
        self.assertEqual(self.profile()["revision"], 8)

    def test_ammo_after_crew_and_crew_after_ammo_preserve_both_domains(self):
        self.activate(); self.ammo(); loaded = deepcopy(self.profile()["ammunition"])
        self.recruit(self.request(expected_revision=7, wire_revision=2))
        crew = deepcopy(self.profile()["crew_inventory"])
        self.assertEqual(self.profile()["ammunition"], loaded)
        self.ammo(command_key="ammo-later", expected_revision=8, wire_revision=3)
        self.assertEqual(self.profile()["crew_inventory"], crew)
        self.assertEqual(len(self.public()["crew"]), 3)
        self.assertEqual(self.public()["crew"][1]["vehicle_inventory_id"], None)

    def test_second_new_command_rejects_exhausted_quota_and_does_not_allocate_id4(self):
        self.activate(); self.recruit()
        self.reject("FREE_RECRUITMENT_EXHAUSTED", lambda: self.recruit(self.request(command_key="second", expected_revision=7, wire_revision=2)))

    def test_foreign_subject_and_native_identity_reject_before_replay(self):
        self.activate(); self.recruit()
        self.reject("FOREIGN_ACCOUNT", lambda: self.store.recruit(self.request(), authenticated_account_id="foreign"))
        self.reject("FOREIGN_ACCOUNT", lambda: self.recruit(self.request(native_database_id=self.native_id + 1)))

    def test_stale_and_paid_or_wrong_vehicle_selection_do_not_mutate(self):
        self.activate()
        self.reject("STALE_REVISION", lambda: self.recruit(self.request(expected_revision=5)))
        for layout in ([3, 1, 1, 1], [3, 1, 1, 2], [3, 2, 1, 0], [3, 1, 0, 0]):
            with self.subTest(layout=layout):
                self.reject("RECRUIT_SELECTION_UNSUPPORTED", lambda: self.recruit(self.request(layout=layout)))
        self.reject("SHOP_REVISION_MISMATCH", lambda: self.recruit(self.request(layout=[4, 1, 1, 0])))

    def test_reserved_vehicle_rejects_recruitment_without_unassigning_driver(self):
        self.activate()
        # Consistent private fixture, not a native battle-admission claim.
        vehicle_id = self.public()["inventory"][0]["inventory_id"]
        self.store.connection.execute("BEGIN IMMEDIATE")
        self.store.connection.execute("UPDATE game_vehicle SET state='reserved',battle_id='private-battle' "
                                      "WHERE account_id=? AND vehicle_id=?", (self.account, vehicle_id))
        AmmoServiceStore._save_snapshot(self.store, self.account, 7)
        aggregate = json.loads(self.store.connection.execute("SELECT snapshot_json FROM game_snapshot WHERE account_id=?", (self.account,)).fetchone()[0])
        self.store.connection.execute("UPDATE game_profiles SET profile_json=? WHERE account_id=?",
            (canonical(self.store._project_profile(self.account, aggregate)).decode(), self.account))
        self.store.connection.commit()
        self.reject("VEHICLE_RESERVED", lambda: self.recruit(self.request(expected_revision=7)))

    def test_strict_request_bounds_reject_boolean_integer_aliases_and_unknown_fields(self):
        self.activate()
        cases = [self.request(expected_revision=True), self.request(native_database_id=True),
                 self.request(wire_revision=True), self.request(layout=[3, 1, True, 0]),
                 self.request(layout=[3, 1, 1]), self.request(command_key="x" * 97),
                 {**self.request(), "client_price": 0}]
        for request in cases:
            with self.subTest(request=request):
                self.reject("INVALID_INPUT", lambda: self.recruit(request))

    def test_shared_ledger_rejects_cross_family_command_key_reuse(self):
        self.activate(); self.recruit()
        self.reject("DUPLICATE_PAYLOAD_MISMATCH", lambda: self.ammo(command_key=self.request()["command_key"], expected_revision=7, wire_revision=2))

    def test_recruit_refuses_an_existing_ammo_command_key(self):
        self.activate(); self.ammo()
        self.reject("DUPLICATE_PAYLOAD_MISMATCH", lambda: self.recruit(
            self.request(command_key=self.ammo_request()["command_key"], expected_revision=7, wire_revision=2)))

    def test_replayed_key_rejects_changed_wire_cursor_and_payload(self):
        self.activate(); self.recruit()
        self.reject("DUPLICATE_PAYLOAD_MISMATCH", lambda: self.recruit(self.request(wire_revision=2)))
        self.reject("DUPLICATE_PAYLOAD_MISMATCH", lambda: self.recruit(self.request(expected_revision=7)))

    def test_all_recruit_write_failpoints_restore_ids_quota_old_assignment_and_ledgers(self):
        self.activate(); before = self.state()
        for point in ("after_old_driver_unassigned", "after_tankman_insert", "after_crew_quota_update",
                      "after_snapshot_update", "after_profile_projection", "after_crew_ledger_insert", "before_commit"):
            with self.subTest(point=point):
                self.store.failpoint = point
                self.reject("INJECTED_FAILURE", lambda: self.recruit())
                self.reopen(); self.assertEqual(self.state(), before)
        self.assertEqual(self.recruit()["status"], "recruited")

    def test_migration_failure_rolls_back_extension_ddl_quota_and_profile(self):
        before = self.state(); self.store.failpoint = "before_crew_migration_commit"
        self.reject("INJECTED_FAILURE", lambda: self.activate())
        self.assertEqual(self.state(), before)
        self.store.failpoint = None; self.activate()

    def test_legacy_ammo_writer_and_activation_refuse_crew_projection_without_changes(self):
        self.activate(); self.recruit(); before = self.state()
        with NativeAmmoStore(self.database) as legacy:
            legacy.initialize()
            with self.assertRaises(TransactionError):
                legacy.service(self.ammo_request(expected_revision=7), authenticated_account_id=self.account)
            with self.assertRaises(TransactionError):
                legacy.migrate(self.source, account_id=self.account, original_root=self.original, grant=GRANT)
        self.assertEqual(self.state(), before)

    def test_corrupt_descriptor_or_allocator_cannot_be_overwritten_by_ammo(self):
        self.activate()
        self.store.connection.execute("UPDATE p04d_crew_member SET descriptor_hex=? WHERE account_id=? AND native_id=2", ("00" * 25, self.account))
        self.store.connection.commit()
        self.reject("CORRUPT_STORE", lambda: self.ammo())
        self.reject("CORRUPT_STORE", lambda: self.recruit())

    def test_allocator_corruption_and_source_audit_pin_change_are_detected(self):
        self.activate()
        for field, value in (("next_native_id", 4), ("next_native_id", 2147483647),
                             ("source_audit_sha256", "0" * 64)):
            with self.subTest(field=field, value=value):
                original = self.store.connection.execute(f"SELECT {field} FROM p04d_crew_meta WHERE account_id=?", (self.account,)).fetchone()[0]
                self.store.connection.execute(f"UPDATE p04d_crew_meta SET {field}=? WHERE account_id=?", (value, self.account))
                self.store.connection.commit()
                self.reject("CORRUPT_STORE", lambda: self.recruit())
                self.store.connection.execute(f"UPDATE p04d_crew_meta SET {field}=? WHERE account_id=?", (original, self.account))
                self.store.connection.commit()

    def test_corrupt_replay_response_and_even_rehashed_wrong_crew_identity_are_rejected(self):
        self.activate(); self.recruit()
        row = self.store.connection.execute("SELECT result_json FROM game_command_ledger WHERE command_type=?", (COMMAND,)).fetchone()
        result = json.loads(row[0]); result["native_inventory_id"] = 4; raw = canonical(result)
        self.store.connection.execute("UPDATE game_command_ledger SET result_json=?,p09c_result_sha256=? WHERE command_type=?",
                                      (raw.decode(), hashlib.sha256(raw).hexdigest(), COMMAND)); self.store.connection.commit()
        self.reject("CORRUPT_STORE", lambda: self.recruit())

    def test_fixture_relogin_rebuilds_mutable_crew_quota_and_preserves_ammo_metadata(self):
        fixture_root = Path(self.temp.name) / "fixtures"
        if os.name == "nt":
            # Same owned evidence directory, without Win32's legacy MAX_PATH.
            fixture_root = Path("\\\\?\\" + str(fixture_root.resolve()))
        self.activate(); first = self.store.publish(self.source, self.account, fixture_root)
        self.recruit(); self.ammo(expected_revision=7, wire_revision=2)
        self.reopen(); result = self.store.publish(self.source, self.account, fixture_root)
        directory = Path(result["fixture_dir"])
        self.assertNotEqual(directory, Path(first["fixture_dir"]))
        files = self.source.fixture_files(self.public(), self.profile(), self.store.layouts(self.account))
        self.assertEqual({p.name: p.read_bytes() for p in directory.iterdir()}, files)
        crew_info = json.loads(files["crew-service.json"]); ammo_info = json.loads(files["ammo-service.json"])
        self.assertEqual((crew_info["free_recruitment_left"], crew_info["configuration_revision"]), (0, 2))
        self.assertEqual(crew_info["policy_sha256"], POLICY_SHA256)
        self.assertFalse(crew_info["battle"]); self.assertFalse(ammo_info["battle"])
        self.assertEqual(crew_info["state_sha256"], hashlib.sha256(files["state.bin"]).hexdigest())
        self.assertEqual(ammo_info["state_sha256"], crew_info["state_sha256"])
        self.assertEqual(crew_info["revision"], self.profile()["revision"])
        self.assertEqual(json.loads(files["manifest.json"])["profile_version"], 6)
        manifest = json.loads(files["manifest.json"])
        for member in manifest["files"]:
            actual = files[member["file"]]
            self.assertEqual((member["bytes"], member["sha256"]), (len(actual), hashlib.sha256(actual).hexdigest()))
        self.assertEqual(manifest["shop_policy"]["source_shop_sha256"], hashlib.sha256(self.source.raw["shop.bin"]).hexdigest())
        self.assertEqual(manifest["shop_policy"]["projected_shop_sha256"], hashlib.sha256(files["shop.bin"]).hexdigest())
        self.assertEqual(self.store.publish(self.source, self.account, fixture_root), result)

    def test_fixture_publication_refuses_ammo_only_projection_source(self):
        self.activate(); self.recruit()
        target = Path(self.temp.name) / "rejected-fixtures"
        legacy_source = ProjectionSource(BUNDLE)
        self.reject("CREW_PROJECTION_REQUIRED", lambda: self.store.publish(legacy_source, self.account, target))
        self.assertFalse(target.exists())

    def race(self, operations):
        barrier = threading.Barrier(2)
        def invoke(operation):
            method, request = operation
            with NativeCrewStore(self.database) as store:
                store.initialize(); barrier.wait(timeout=10)
                try:
                    return ("ok", getattr(store, method)(request, authenticated_account_id=self.account))
                except TransactionError as error:
                    return ("error", error.code)
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(invoke, operation) for operation in operations]
            return [f.result(timeout=15) for f in futures]

    def test_two_connections_same_recruit_commit_once_and_replay_once(self):
        self.activate(); request = self.request()
        replies = self.race([("recruit", request), ("recruit", request)])
        self.assertEqual([kind for kind, _ in replies], ["ok", "ok"])
        self.assertEqual(sorted(row["replayed"] for _, row in replies), [False, True])
        self.assertEqual(len(self.profile()["crew_inventory"]["members"]), 3)
        self.assertEqual(self.profile()["revision"], 7)
        self.assertEqual(self.store.ledger_count(self.account), 1)

    def test_two_connections_ammo_and_recruit_share_one_revision(self):
        self.activate()
        replies = self.race([("recruit", self.request()), ("service", self.ammo_request())])
        self.assertEqual(sorted(kind for kind, _ in replies), ["error", "ok"])
        self.assertEqual(next(value for kind, value in replies if kind == "error"), "STALE_REVISION")
        self.assertEqual(self.profile()["revision"], 7)
        self.assertEqual(self.store.ledger_count(self.account), 1)
        winner = next(value for kind, value in replies if kind == "ok")
        self.assertEqual(len(self.profile()["crew_inventory"]["members"]), 3 if winner["status"] == "recruited" else 2)


if __name__ == "__main__":
    unittest.main()
