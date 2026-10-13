"""Real SQLite/source migrations and shared crew/ammo writes, no native claim."""
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
from p04f_crew_store import NativeCrewTransferStore, COMMAND, RECRUIT_COMMAND
from p04f_crew_projection import CrewTransferProjectionSource, canonical, POLICY_SHA256, native_crew
from p04d_crew_store import NativeCrewStore
from p09d_ammo_store import NativeAmmoStore
from p09c_ammo_service import AmmoServiceStore
from game_profile_tx import TransactionError

TEMP = ROOT / "local/tests/p04f-store"
GRANT = {"grant_id": "p09d-test-depot-v1", "quantity_each": 100}


class TransferStoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        bundle = os.environ.get("P04F_TEST_BUNDLE") or os.environ.get("P04D_TEST_BUNDLE")
        config = Path(os.environ.get("WOT091_CONFIG", ROOT / "config/project.local.json"))
        if not bundle or not config.is_file():
            raise unittest.SkipTest("NOT_RUN: P04F_TEST_BUNDLE and WOT091_CONFIG required")
        cls.source = CrewTransferProjectionSource(bundle)
        cls.original = Path(json.loads(config.read_text(encoding="utf-8-sig"))["paths"]["original_client_root"])
        cls.account = cls.source.profile["account_id"]
        cls.native_id = cls.source.profile["native_database_id"]

    def setUp(self):
        TEMP.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix="case-", dir=TEMP)
        self.addCleanup(self.temp.cleanup)
        self.database = Path(self.temp.name) / "game.sqlite"
        with closing(sqlite3.connect(self.database)) as c:
            c.executescript("""PRAGMA user_version=1;
                CREATE TABLE game_meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
                CREATE TABLE game_profiles(native_id INTEGER PRIMARY KEY AUTOINCREMENT,account_id TEXT NOT NULL UNIQUE,profile_json TEXT NOT NULL);
                CREATE TABLE game_limits(key_hash TEXT PRIMARY KEY,hits INTEGER NOT NULL,resets_at INTEGER NOT NULL);""")
            c.execute("INSERT INTO game_profiles VALUES (?,?,?)", (self.native_id, self.account, canonical(self.source.profile).decode()))
            c.execute("INSERT INTO game_profiles VALUES (999,?,?)", ("untouched-account", '{"unrelated":true}'))
            c.execute("INSERT INTO game_meta VALUES ('unrelated','preserve-me')")
            c.commit()
        with NativeCrewStore(self.database) as old:
            old.migrate(self.source, account_id=self.account, original_root=self.original, grant=GRANT)
            old.migrate_crew(self.source, account_id=self.account, original_root=self.original)
        self.store = NativeCrewTransferStore(self.database)
        self.addCleanup(lambda: self.store.close())

    def old_request(self):
        return dict(account_id=self.account, native_database_id=self.native_id, command_key="old-recruit",
            expected_revision=6, wire_revision=1, layout=[3, 1, 1, 0])

    def activate(self, recruited=True):
        if recruited:
            with NativeCrewStore(self.database) as old:
                old.recruit(self.old_request(), authenticated_account_id=self.account)
        return self.store.migrate_transfer(self.source, account_id=self.account, original_root=self.original)

    def profile(self):
        return self.store.read_profile(self.account)

    def public(self):
        return json.loads(self.store.connection.execute("SELECT profile_json FROM game_profiles WHERE account_id=?", (self.account,)).fetchone()[0])

    def request(self, layout=None, **changes):
        revision = self.profile()["revision"]
        value = dict(account_id=self.account, native_database_id=self.native_id,
            command_key="transfer-" + str(revision), expected_revision=revision, wire_revision=1,
            layout=[1, 1, -1] if layout is None else layout)
        value.update(changes)
        return value

    def transfer(self, layout=None, **changes):
        return self.store.transfer(self.request(layout, **changes), authenticated_account_id=self.account)

    def recruit(self, **changes):
        return self.store.recruit(self.request([3, 1, 1, 0], **changes), authenticated_account_id=self.account)

    def ammo(self, **changes):
        return self.store.service(self.request([3, 1, 6, 2570, 30, 2826, 10, 3082, 5, 6, 0, 0, 0, 0, 0, 0], **changes), authenticated_account_id=self.account)

    def state(self):
        return list(self.store.connection.iterdump())

    def reopen(self):
        self.store.close(); self.store = NativeCrewTransferStore(self.database); self.store.initialize()

    def reject(self, code, operation):
        before = self.state()
        with self.assertRaises(TransactionError) as caught:
            operation()
        self.assertEqual(caught.exception.code, code)
        self.assertEqual(self.state(), before)
        self.assertFalse(self.store.connection.in_transaction)

    def test_explicit_migration_required_and_preserves_two_tankmen(self):
        self.reject("P04F_MIGRATION_REQUIRED", self.store.initialize)
        result = self.activate(False)
        self.assertEqual((result["revision"], result["retained_tankmen"], result["new_tankmen"]), (7, 2, 0))
        self.assertEqual(self.public()["profile_version"], 7)
        self.assertEqual(self.public()["crew"], self.source.profile["crew"])
        self.assertEqual(self.profile()["crew_inventory"]["configuration_revision"], 1)

    def test_recruited_migration_retains_all_ids_ammo_resources_and_ledger(self):
        with NativeCrewStore(self.database) as old:
            old.recruit(self.old_request(), authenticated_account_id=self.account)
            before = old.read_profile(self.account)
        result = self.store.migrate_transfer(self.source, account_id=self.account, original_root=self.original)
        after = self.profile()
        self.assertEqual(result["revision"], 8)
        for field in ("ammunition", "depot", "vehicles"):
            self.assertEqual(before[field], after[field])
        expected = deepcopy(before["crew_inventory"]); expected["policy_sha256"] = POLICY_SHA256
        self.assertEqual(after["crew_inventory"], expected)
        self.assertEqual(self.public()["resources"], self.source.profile["resources"])
        self.assertEqual(self.store.ledger_count(self.account), 1)

    def test_migration_reopen_repetition_never_restores_assignment_or_quota(self):
        self.activate(); self.transfer(); self.reopen(); before = self.state()
        self.assertEqual(self.store.migrate_transfer(self.source, account_id=self.account, original_root=self.original)["status"], "already_migrated")
        self.assertEqual(self.state(), before)

    def test_migration_failpoint_rolls_back_schema_projection_and_policy(self):
        self.store.failpoint = "before_transfer_migration_commit"
        self.reject("INJECTED_FAILURE", lambda:self.activate(False))
        self.store.failpoint = None
        self.assertEqual(self.activate(False)["status"], "migrated")

    def test_migration_rejects_changed_source_bundle_or_previous_source_audit(self):
        original = self.source.bundle_sha256
        try:
            self.source.bundle_sha256 = "0" * 64
            self.reject("MIGRATION_SOURCE_CHANGED", lambda:self.activate(False))
        finally:
            self.source.bundle_sha256 = original
        c = self.store.connection
        c.execute("UPDATE p04d_crew_meta SET source_audit_sha256=?", ("0" * 64,)); c.commit()
        self.reject("MIGRATION_SOURCE_CHANGED", lambda:self.activate(False))

    def test_unknown_transfer_schema_rejects_reopen(self):
        self.activate(); self.store.connection.execute("UPDATE p04f_schema SET version='unknown'"); self.store.connection.commit()
        self.reject("UNSUPPORTED_STORE_SCHEMA", self.store.initialize)

    def test_old_writers_reject_after_transfer_migration(self):
        self.activate(); before = self.state()
        with NativeCrewStore(self.database) as old:
            with self.assertRaises(TransactionError): old.initialize()
            with self.assertRaises(TransactionError): old.recruit(self.old_request(), authenticated_account_id=self.account)
        with NativeAmmoStore(self.database) as old:
            with self.assertRaises(TransactionError): old.read_profile(self.account)
            with self.assertRaises(TransactionError): old.migrate(self.source, account_id=self.account, original_root=self.original, grant=GRANT)
        self.assertEqual(self.state(), before)

    def test_unload_fill_and_occupied_replacement_preserve_every_identity(self):
        self.activate(); initial = self.profile(); rows = deepcopy(initial["crew_inventory"]["members"])
        reply = self.transfer()
        self.assertEqual((reply["status"], reply["revision"], reply["wire_revision"]), ("transferred", 9, 2))
        self.assertEqual(native_crew(self.profile()["crew_inventory"])[1], [1, None])
        self.assertFalse(self.public()["inventory"][0]["crew_assigned"])
        self.transfer([1, 1, 2]); self.assertEqual(native_crew(self.profile()["crew_inventory"])[1], [1, 2])
        self.transfer([1, 1, 3]); self.assertEqual(native_crew(self.profile()["crew_inventory"])[1], [1, 3])
        self.assertEqual(self.profile()["crew_inventory"]["members"], rows)
        self.assertEqual(self.profile()["crew_inventory"]["configuration_revision"], 5)
        self.assertEqual(initial["ammunition"], self.profile()["ammunition"])
        self.assertEqual(initial["depot"], self.profile()["depot"])

    def test_whole_crew_unload_is_one_atomic_revision_and_relogin_vacancy(self):
        self.activate(); before = self.profile(); self.transfer([1, -1, -1]); self.reopen()
        after = self.profile()
        self.assertEqual(after["revision"], before["revision"] + 1)
        self.assertEqual(after["crew_inventory"]["configuration_revision"], 3)
        self.assertEqual(native_crew(after["crew_inventory"])[1], [None, None])
        self.assertTrue(all(r["vehicle_inventory_id"] is None for r in self.public()["crew"]))
        self.transfer([1, 0, 1]); self.assertEqual(native_crew(self.profile()["crew_inventory"])[1], [1, None])

    def test_noops_reject_without_ledger_or_revision(self):
        self.activate(); self.reject("NO_ASSIGNMENT_CHANGE", lambda:self.transfer([1, 1, 3]))
        self.transfer([1, -1, -1])
        self.reject("NO_ASSIGNMENT_CHANGE", lambda:self.transfer([1, -1, -1]))
        self.reject("NO_ASSIGNMENT_CHANGE", lambda:self.transfer([1, 0, -1]))

    def test_foreign_identity_and_native_id_reject_before_replay(self):
        self.activate(); request = self.request(); self.store.transfer(request, authenticated_account_id=self.account)
        self.reject("FOREIGN_ACCOUNT", lambda:self.store.transfer(request, authenticated_account_id="someone-else"))
        self.reject("FOREIGN_ACCOUNT", lambda:self.store.transfer({**request,"native_database_id":999}, authenticated_account_id=self.account))

    def test_wrong_vehicle_role_slot_and_unknown_tankman_reject(self):
        self.activate()
        for layout, code in (([2, 1, -1], "UNKNOWN_VEHICLE"), ([1, 0, 2], "INCOMPATIBLE_CREW_ROLE"),
            ([1, 1, 1], "INCOMPATIBLE_CREW_ROLE"), ([1, -1, 3], "TRANSFER_SELECTION_UNSUPPORTED"),
            ([1, 5, -1], "TRANSFER_SELECTION_UNSUPPORTED"), ([1, 1, 99], "UNKNOWN_TANKMAN")):
            self.reject(code, lambda:self.transfer(layout))

    def test_malformed_boolean_oversize_and_extra_fields_reject(self):
        self.activate()
        for changes in ({"layout":[1,True,-1]}, {"layout":[1,1]}, {"layout":[1,1,2**31]},
            {"expected_revision":True}, {"wire_revision":0}, {"native_database_id":True},
            {"command_key":"x"*97}, {"client_price":0}):
            request = self.request(); request.update(changes)
            self.reject("INVALID_INPUT", lambda:self.store.transfer(request, authenticated_account_id=self.account))

    def test_stale_revision_rejects_before_assignment(self):
        self.activate(); self.reject("STALE_REVISION", lambda:self.transfer(expected_revision=7))

    def test_reserved_vehicle_refuses_even_whole_crew_unload(self):
        self.activate(); profile = self.public(); c = self.store.connection
        c.execute("BEGIN IMMEDIATE")
        c.execute("UPDATE game_vehicle SET state='reserved',battle_id='synthetic-battle' WHERE account_id=? AND vehicle_id=?", (self.account, profile["inventory"][0]["inventory_id"]))
        old = c.execute("SELECT profile_json FROM game_profiles WHERE account_id=?", (self.account,)).fetchone()[0]
        self.store._save_crew_projection(self.account, 9, old); c.commit()
        self.reject("VEHICLE_RESERVED", lambda:self.transfer([1,-1,-1]))

    def test_ammo_before_and_after_transfer_preserves_partial_crew(self):
        self.activate(); self.ammo(); ammo = self.profile()["ammunition"]
        self.transfer(); crew = self.profile()["crew_inventory"]
        self.ammo(command_key="second-ammo"); self.assertEqual(self.profile()["crew_inventory"], crew)
        self.assertEqual(self.profile()["ammunition"], ammo)

    def test_recruitment_after_vacancy_retains_barracks_driver_and_missing_commander(self):
        self.activate(False); self.transfer([1,-1,-1]); reply = self.recruit()
        self.assertEqual(reply["status"], "recruited")
        self.assertEqual(native_crew(self.profile()["crew_inventory"])[1], [None,3])
        self.assertEqual([r["vehicle_native_id"] for r in self.profile()["crew_inventory"]["members"]], [-1,-1,1])
        self.assertFalse(self.public()["inventory"][0]["crew_assigned"])
        self.reject("FREE_RECRUITMENT_EXHAUSTED", lambda:self.recruit())

    def test_recruitment_replaces_occupied_driver_after_transfers(self):
        self.activate(False); self.transfer([1,0,-1]); self.transfer([1,0,1]); self.recruit()
        self.assertEqual(native_crew(self.profile()["crew_inventory"])[1], [1,3])
        self.assertEqual(self.profile()["crew_inventory"]["configuration_revision"], 4)

    def test_transfer_replay_after_later_reassignment_and_reopen_is_original_response(self):
        self.activate(); request = self.request(); first = self.store.transfer(request, authenticated_account_id=self.account)
        self.transfer([1,1,2]); self.ammo(); self.reopen(); before = self.state()
        self.assertEqual(self.store.transfer(request, authenticated_account_id=self.account), {**first,"replayed":True})
        self.assertEqual(self.state(), before)

    def test_recruitment_replay_after_new_assignments_is_original_response(self):
        self.activate(False); request = self.request([3,1,1,0]); first = self.store.recruit(request, authenticated_account_id=self.account)
        self.transfer([1,-1,-1]); self.reopen(); before = self.state()
        self.assertEqual(self.store.recruit(request, authenticated_account_id=self.account), {**first,"replayed":True})
        self.assertEqual(self.state(), before)

    def test_accepted_p04d_recruit_replays_after_migration_and_transfers(self):
        self.activate(); self.transfer([1,-1,-1]); self.reopen(); before = self.state()
        reply = self.store.recruit(self.old_request(), authenticated_account_id=self.account)
        self.assertEqual((reply["status"],reply["revision"],reply["replayed"]), ("recruited",7,True))
        self.assertEqual(self.state(), before)

    def test_shared_namespace_and_changed_replay_reject(self):
        self.activate(); request = self.request(); self.store.transfer(request, authenticated_account_id=self.account)
        self.reject("DUPLICATE_PAYLOAD_MISMATCH", lambda:self.ammo(command_key=request["command_key"]))
        self.reject("DUPLICATE_PAYLOAD_MISMATCH", lambda:self.store.transfer({**request,"wire_revision":2}, authenticated_account_id=self.account))
        self.ammo(); key = "transfer-" + str(self.profile()["revision"] - 1)
        self.reject("DUPLICATE_PAYLOAD_MISMATCH", lambda:self.transfer([1,1,2],command_key=key))

    def test_all_mutation_failpoints_restore_assignments_revisions_and_ledgers(self):
        self.activate(); before = self.state()
        for point in ("after_transfer_unassign", "after_transfer_assign", "after_transfer_meta_update",
            "after_snapshot_update", "after_profile_projection", "after_transfer_ledger_insert", "before_commit"):
            self.store.failpoint = point
            self.reject("INJECTED_FAILURE", lambda:self.transfer([1,-1,-1]))
            self.reopen(); self.assertEqual(self.state(), before)

    def test_configuration_exhaustion_rejects_without_partial_unload(self):
        self.activate(); c = self.store.connection; old = c.execute("SELECT profile_json FROM game_profiles WHERE account_id=?", (self.account,)).fetchone()[0]
        c.execute("BEGIN IMMEDIATE"); c.execute("UPDATE p04d_crew_meta SET configuration_revision=?", (2**31-1,))
        self.store._save_crew_projection(self.account, 9, old); c.commit()
        self.reject("REVISION_EXHAUSTED", self.transfer)

    def test_corrupt_assignment_or_descriptor_cannot_be_overwritten(self):
        self.activate(); self.store.connection.execute("UPDATE p04d_crew_member SET descriptor_hex=? WHERE native_id=3", ("00"*25,)); self.store.connection.commit()
        self.reject("CORRUPT_STORE", lambda:self.store.transfer(dict(self.old_request(),layout=[1,1,-1]),authenticated_account_id=self.account))
        with self.assertRaises(TransactionError): self.profile()

    def test_rehashed_impossible_replay_transition_rejects(self):
        self.activate(); request=self.request(); self.store.transfer(request,authenticated_account_id=self.account)
        c=self.store.connection; row=c.execute("SELECT result_json FROM game_command_ledger WHERE command_type=?",(COMMAND,)).fetchone()
        result=json.loads(row[0]); result["after_crew"]["members"][0].update(vehicle_native_id=-1,seat=None); raw=canonical(result)
        c.execute("UPDATE game_command_ledger SET result_json=?,p09c_result_sha256=? WHERE command_type=?",(raw.decode(),hashlib.sha256(raw).hexdigest(),COMMAND)); c.commit()
        self.reject("CORRUPT_STORE",lambda:self.store.transfer(request,authenticated_account_id=self.account))

    def test_fixture_partial_crew_metadata_and_ammo_share_native_state_hash(self):
        self.activate(); self.transfer([1,-1,-1]); self.transfer([1,0,1]); self.reopen()
        root=Path(self.temp.name)/"fixtures"
        if os.name == "nt": root=Path("\\\\?\\"+str(root.resolve()))
        published=self.store.publish(self.source,self.account,root); directory=Path(published["fixture_dir"])
        files={p.name:p.read_bytes() for p in directory.iterdir()}
        self.assertNotIn("crew-service.json",files)
        metadata=json.loads(files["crew-transfer.json"]); ammo=json.loads(files["ammo-service.json"])
        self.assertEqual(set(metadata),{"version","account_id","native_database_id","revision","wire_revision","policy_sha256","state_sha256","command","vehicle_inventory_id","free_recruitment_left","configuration_revision","battle"})
        self.assertEqual(metadata["state_sha256"],hashlib.sha256(files["state.bin"]).hexdigest())
        self.assertEqual(metadata["state_sha256"],ammo["state_sha256"])
        self.assertEqual(metadata["command"],105); self.assertEqual(json.loads(files["manifest.json"])["profile_version"],7)
        self.assertEqual(self.store.publish(self.source,self.account,root),published)

    def test_two_connections_same_command_commit_once(self):
        self.activate(); request=self.request(); barrier=threading.Barrier(2)
        def perform(_):
            with NativeCrewTransferStore(self.database) as store:
                barrier.wait(); return store.transfer(request,authenticated_account_id=self.account)
        with ThreadPoolExecutor(2) as pool: replies=list(pool.map(perform,range(2)))
        self.assertEqual(sorted(row["replayed"] for row in replies),[False,True])
        self.assertEqual(self.profile()["revision"],9)

    def test_two_connections_transfer_and_ammo_have_one_revision_winner(self):
        self.activate(); barrier=threading.Barrier(2)
        requests=[self.request(),self.request([3,1,6,2570,30,2826,10,3082,5,6,0,0,0,0,0,0],command_key="race-ammo")]
        def perform(index):
            with NativeCrewTransferStore(self.database) as store:
                barrier.wait()
                try:return ("ok",(store.transfer if index==0 else store.service)(requests[index],authenticated_account_id=self.account))
                except TransactionError as error:return ("error",error.code)
        with ThreadPoolExecutor(2) as pool: replies=list(pool.map(perform,range(2)))
        self.assertEqual(sorted(kind for kind,_ in replies),["error","ok"])
        self.assertEqual(next(value for kind,value in replies if kind=="error"),"STALE_REVISION")
        self.assertEqual(self.profile()["revision"],9)
