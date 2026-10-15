"""Real isolated profile13 SQLite journal; synthetic authoritative result DTOs."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import unittest
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from tests import test_p08b_battle_store as previous
from p08c_battle_results import ResultsStore, canonical, results_service, validate_request
from game_profile_tx import TransactionError


class ResultsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        previous.BattleStoreTests.setUpClass.__func__(cls)

    activate = previous.BattleStoreTests.activate
    profile = previous.BattleStoreTests.profile
    public = previous.BattleStoreTests.public
    state = previous.BattleStoreTests.state
    old_request = previous.BattleStoreTests.old_request
    request = previous.BattleStoreTests.request
    call = previous.BattleStoreTests.call
    start = previous.BattleStoreTests.start
    reject = previous.BattleStoreTests.reject

    def setUp(self):
        previous.BattleStoreTests.setUp(self)
        self.store.close(); self.store = ResultsStore(self.database, self.catalog)
        self.arena = "9007199254740993"

    def result(self):
        own = dict(vehicle_id=152043523, account_dbid=self.native_id, name="Авторитетный", team=1,
            type_compact_descr=3329, health=23, shots=3, direct_hits=1, piercings=1, damage_dealt=7,
            damage_received=67, kills=0, capture_points=42, dropped_capture_points=3, mileage_metres=135,
            life_time=90, killer_id=0, death_reason=-1, premature_leave=False)
        enemy = dict(own, vehicle_id=152043524, account_dbid=self.native_id + 1, name="Synthetic peer", team=2,
            health=83, shots=1, damage_received=7, damage_dealt=67, capture_points=0)
        return dict(arena_id=int(self.arena), arena_type_id=4, created_unix=1792080000, winner_team=1,
            finish_reason=1, duration_seconds=120, participants=[own, enemy])

    def finished(self, reason="battle_finished"):
        _, admitted = self.start(battle_id=self.run + ":" + self.arena)
        request = self.request("finish", battle_id=self.run + ":" + self.arena,
            reservation_id=admitted["reservation"]["reservation_id"], remaining_ap=17, terminal_hp=23, reason=reason)
        if reason == "battle_finished": request["results_json"] = canonical(self.result()).decode("ascii")
        self.store.battle(request, authenticated_account_id=self.account)
        return admitted["reservation"]

    def results_request(self, operation="store", reservation=None, **changes):
        self.serial += 1
        request = dict(version=1, operation=operation, account_id=self.account, native_database_id=self.native_id,
            command_key="results-test:" + str(self.serial), arena_id=self.arena)
        if operation == "store":
            request.update(run_id=self.run, battle_id=self.run + ":" + self.arena, native_inventory_id=1,
                reservation_id=reservation["reservation_id"], results_json=canonical(self.result()).decode("ascii"))
        request.update(changes); return request

    def send(self, request):
        return self.store.results(request, authenticated_account_id=self.account)

    def test_actual_finish_journal_query_ack_replay_and_reopen_preserve_profile(self):
        receipt = self.finished(); before = deepcopy(self.profile()); resources = self.public()["resources"]
        self.assertEqual(self.store.connection.execute("SELECT COUNT(*) FROM p08c_result").fetchone()[0], 1)
        request = self.results_request(reservation=receipt); response = self.send(request)
        self.assertEqual((response["status"], response["arena_id"], response["acked"]), ("stored", self.arena, False))
        self.assertEqual(json.loads(response["results_json"]), self.result())
        self.assertEqual(self.send(request), dict(response, replayed=True))
        self.assertEqual(self.profile(), before); self.assertEqual(self.public()["resources"], resources)
        self.store.close(); self.store = ResultsStore(self.database, self.catalog)
        query = self.results_request("query"); self.assertEqual(self.send(query)["results_json"], response["results_json"])
        ack = self.results_request("ack"); acked = self.send(ack)
        self.assertEqual((acked["status"], acked["acked"]), ("acked", True))
        snapshot = self.state(); self.assertEqual(self.send(ack), dict(acked, replayed=True)); self.assertEqual(self.state(), snapshot)
        self.assertTrue(self.send(query)["acked"]); self.assertEqual(self.profile(), before)
        # A recorded store replay retains its original receipt, even after ack.
        self.assertEqual(self.send(request), dict(response, replayed=True))

    def test_active_manual_and_restart_abort_never_manufacture_finished_battle_results(self):
        _, admission = self.start(battle_id=self.run + ":" + self.arena)
        request = self.results_request(reservation=admission["reservation"])
        self.reject("RESULT_NOT_READY", lambda: self.send(request))
        finish = self.request("finish", battle_id=self.run + ":" + self.arena,
            reservation_id=admission["reservation"]["reservation_id"], remaining_ap=17, terminal_hp=23, reason="manual_leave")
        self.store.battle(finish, authenticated_account_id=self.account)
        self.reject("RESULT_NOT_READY", lambda: self.send(request))
        self.assertEqual(results_service(self.store, request, authenticated_account_id=self.account)["code"], "RESULT_NOT_READY")

    def test_owner_run_arena_inventory_loadout_hp_and_shots_bind_exact_finished_reservation(self):
        receipt = self.finished(); valid = self.results_request(reservation=receipt)
        for changes in ({"native_inventory_id": 2}, {"reservation_id": "unknown"},
            {"run_id": str(uuid.uuid4()), "battle_id": str(uuid.uuid4()) + ":" + self.arena},
            {"native_database_id": self.native_id + 1}, {"account_id": str(uuid.uuid4())}):
            bad = dict(valid, **changes); before = self.state()
            with self.assertRaises(TransactionError): self.send(bad)
            self.assertEqual(self.state(), before)
        for field, value in (("health", 24), ("shots", 4), ("type_compact_descr", 7169), ("account_dbid", 9999)):
            result = self.result(); result["participants"][0][field] = value
            with self.assertRaises(TransactionError): self.send(dict(valid, results_json=canonical(result).decode("ascii")))
        self.assertEqual(self.send(valid)["status"], "stored")

    def test_idempotency_key_and_arena_reject_changed_payload_without_mutation(self):
        receipt = self.finished(); request = self.results_request(reservation=receipt); self.send(request)
        changed = self.result(); changed["participants"][0]["capture_points"] += 1
        changed = canonical(changed).decode("ascii")
        self.reject("DUPLICATE_PAYLOAD_MISMATCH", lambda: self.send(dict(request, results_json=changed)))
        self.reject("RESULT_MISMATCH", lambda: self.send(dict(request, command_key="results:new-key", results_json=changed)))
        replay = self.send(dict(request, command_key="results:another-key")); self.assertEqual(replay["status"], "stored")

    def test_strict_dto_bounds_duplicate_keys_float_boolean_unknown_and_depth(self):
        receipt = self.finished(); valid = self.results_request(reservation=receipt)
        values = []
        for field, value in (("arena_id", True), ("arena_id", 2**63), ("winner_team", 3), ("duration_seconds", 3601),
            ("participants", []), ("participants", [self.result()["participants"][0]] * 7)):
            bad = self.result(); bad[field] = value; values.append(json.dumps(bad))
        for field, value in (("shots", 193), ("shots", 3.0), ("health", -1), ("name", "x" * 49),
            ("name", "\x00bad"), ("premature_leave", 0), ("life_time", 121), ("xp", 100)):
            bad = self.result(); bad["participants"][0][field] = value; values.append(json.dumps(bad))
        raw = valid["results_json"]; values.extend((raw.replace('"arena_id":', '"arena_id":1,"arena_id":', 1),
            "[" * 2000 + "]" * 2000, " " * 32769))
        for raw in values:
            with self.subTest(raw=raw[:80]):
                before = self.state()
                with self.assertRaises(TransactionError): self.send(dict(valid, results_json=raw))
                self.assertEqual(self.state(), before)
        for arena in (1, "01", "0", "9223372036854775808", "9007199254740993.0"):
            with self.assertRaises(TransactionError): validate_request(dict(valid, arena_id=arena), self.account)

    def test_store_and_ack_failpoints_rollback_all_rows_and_schema(self):
        _, admitted = self.start(battle_id=self.run + ":" + self.arena); receipt = admitted["reservation"]
        finish = self.request("finish", battle_id=self.run + ":" + self.arena, reservation_id=receipt["reservation_id"],
            remaining_ap=17, terminal_hp=23, reason="battle_finished", results_json=canonical(self.result()).decode("ascii"))
        for point in ("after_results_schema", "after_results_insert", "after_battle_ledger", "before_battle_commit"):
            self.store.failpoint = point
            self.reject("INJECTED_FAILURE", lambda: self.store.battle(finish, authenticated_account_id=self.account))
        self.store.failpoint = None; self.store.battle(finish, authenticated_account_id=self.account)
        request = self.results_request(reservation=receipt)
        for point in ("after_results_ledger", "before_results_commit"):
            self.store.failpoint = point; self.reject("INJECTED_FAILURE", lambda: self.send(request))
        self.store.failpoint = None; self.send(request); ack = self.results_request("ack")
        for point in ("after_results_ack", "after_results_ledger", "before_results_commit"):
            self.store.failpoint = point; self.reject("INJECTED_FAILURE", lambda: self.send(ack))
        self.store.failpoint = None; self.assertTrue(self.send(ack)["acked"])

    def test_concurrent_exact_store_commits_once_and_corrupt_journal_fails_closed(self):
        receipt = self.finished(); request = self.results_request(reservation=receipt); barrier = threading.Barrier(2)
        def submit():
            with ResultsStore(self.database, self.catalog) as store:
                barrier.wait(); return store.results(request, authenticated_account_id=self.account)
        with ThreadPoolExecutor(max_workers=2) as pool: results = list(pool.map(lambda _: submit(), range(2)))
        self.assertEqual(sorted(r["replayed"] for r in results), [False, True])
        self.assertEqual(self.store.connection.execute("SELECT COUNT(*) FROM p08c_result").fetchone()[0], 1)
        self.store.connection.execute("UPDATE p08c_result SET results_sha256=?", ("0" * 64,)); self.store.connection.commit()
        self.reject("CORRUPT_STORE", lambda: self.send(self.results_request("query")))

    def test_missing_query_ack_and_old_run_reauth_keep_finished_result_readable(self):
        receipt = self.finished(); store = self.results_request(reservation=receipt); self.send(store)
        old = self.run; self.run = str(uuid.uuid4()); self.call("run_open")
        self.assertNotEqual(old, self.run); self.assertEqual(self.send(self.results_request("query"))["status"], "found")
        self.assertEqual(self.send(store)["status"], "stored")
        for op in ("query", "ack"):
            result = self.send(self.results_request(op, arena_id="123"))
            self.assertEqual((result["status"], result["results_json"], result["acked"]), ("missing", None, False))

    def test_same_cli_worker_stores_and_queries_actual_isolated_sqlite(self):
        receipt = self.finished(); request = self.results_request(reservation=receipt)
        argv = [sys.executable, "-B", "-X", "utf8", str(ROOT / "tools/p08b_battle_service.py"),
            "--database", str(self.database), "--bundle", os.environ["P04D_TEST_BUNDLE"], "--original-root", str(self.original),
            "--account-id", self.account, "--fixture-root", str(self.database.parent / "results-fixtures"), "results"]
        for value, status in ((request, "stored"), (self.results_request("query"), "found")):
            ran = subprocess.run(argv, input=canonical(value), capture_output=True, timeout=30, cwd=ROOT)
            self.assertEqual(ran.returncode, 0, ran.stderr.decode("utf-8", "replace"))
            result = json.loads(ran.stdout); self.assertEqual(result["status"], status)
            self.assertEqual(json.loads(result["results_json"])["arena_id"], int(self.arena))

    def test_natural_finish_requires_atomic_complete_results_and_retry_binds_entire_payload(self):
        _, admitted = self.start(battle_id=self.run + ":" + self.arena); receipt = admitted["reservation"]
        finish = self.request("finish", battle_id=self.run + ":" + self.arena, reservation_id=receipt["reservation_id"],
            remaining_ap=17, terminal_hp=23, reason="battle_finished")
        before = self.state()
        with self.assertRaises(TransactionError): self.store.battle(finish, authenticated_account_id=self.account)
        self.assertEqual(self.state(), before)
        bad = self.result(); bad["participants"][0]["health"] = 24
        self.reject("RESULT_MISMATCH", lambda: self.store.battle(dict(finish, results_json=canonical(bad).decode("ascii")), authenticated_account_id=self.account))
        finish["results_json"] = canonical(self.result()).decode("ascii")
        done = self.store.battle(finish, authenticated_account_id=self.account)
        self.assertEqual(self.send(self.results_request("query"))["status"], "found")
        self.assertEqual(self.store.battle(finish, authenticated_account_id=self.account), dict(done, replayed=True))
        padded = dict(finish, results_json=finish["results_json"] + " " * (32768 - len(finish["results_json"])))
        self.assertEqual(self.store.battle(padded, authenticated_account_id=self.account), dict(done, replayed=True))
        bad = self.result(); bad["participants"][0]["capture_points"] += 1
        self.reject("DUPLICATE_PAYLOAD_MISMATCH", lambda: self.store.battle(dict(finish, results_json=canonical(bad).decode("ascii")), authenticated_account_id=self.account))
        self.store.connection.execute("DELETE FROM p08c_result"); self.store.connection.commit()
        self.reject("CORRUPT_STORE", lambda: self.store.battle(finish, authenticated_account_id=self.account))


if __name__ == "__main__": unittest.main()
