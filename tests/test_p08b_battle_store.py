"""Actual isolated profile13 SQLite, reservation/result/fencing and projection."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json
import os
from pathlib import Path
import sys
import subprocess
import threading
import unittest
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from tests import test_p09e_research_store as previous
from p08b_battle_store import BattleStore, POLICY_SHA256, canonical, sha, freeze_loadout
from p08b_battle_projection import BattleProjectionSource, capabilities
from p08b_battle_service import battle_service
from p09e_research_store import ResearchStore
from p09e_research_projection import ResearchProjectionSource
from p09e_research_service import native_service, existing_service
from game_profile_tx import TransactionError


class BattleStoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        previous.ResearchStoreTests.setUpClass.__func__(cls)
        cls.battle_source = BattleProjectionSource(os.environ["P04D_TEST_BUNDLE"], cls.catalog)

    activate = previous.ResearchStoreTests.activate
    profile = previous.ResearchStoreTests.profile
    public = previous.ResearchStoreTests.public
    state = previous.ResearchStoreTests.state
    old_request = previous.ResearchStoreTests.old_request

    def setUp(self):
        previous.ResearchStoreTests.setUp(self)
        self.store.close()
        self.store = BattleStore(self.database, self.catalog)
        if not self._testMethodName.startswith("test_activation_failpoint"):
            self.store.activate(account_id=self.account, authenticated_account_id=self.account)
        self.run = str(uuid.uuid4()); self.serial = 0

    def request(self, operation, **changes):
        self.serial += 1
        value = dict(version=1, operation=operation, account_id=self.account, native_database_id=self.native_id,
            command_key="battle-test:" + str(self.serial), expected_revision=self.profile()["revision"], run_id=self.run)
        if operation in ("admit", "finish"): value.update(battle_id=self.run + ":1", native_inventory_id=1)
        value.update(changes)
        return value

    def call(self, operation, **changes):
        return self.store.battle(self.request(operation, **changes), authenticated_account_id=self.account)

    def start(self, **changes):
        self.call("run_open")
        request = self.request("admit", **changes)
        response = self.store.battle(request, authenticated_account_id=self.account)
        return request, response

    def finish_request(self, admission, **changes):
        return self.request("finish", reservation_id=admission["reservation"]["reservation_id"],
            remaining_ap=17, terminal_hp=23, reason="manual_leave", **changes)

    def reject(self, code, action):
        before = self.state()
        with self.assertRaises(TransactionError) as caught: action()
        self.assertEqual(caught.exception.code, code)
        self.assertEqual(self.state(), before)
        self.assertFalse(self.store.connection.in_transaction)

    def reopen(self):
        self.store.close(); self.store = BattleStore(self.database, self.catalog); self.store.initialize()

    def test_activation_preserves_profile_resources_and_is_idempotent(self):
        before = self.state()
        self.assertEqual(self.store.activate(account_id=self.account, authenticated_account_id=self.account)["status"], "already_active")
        self.assertEqual(self.state(), before)
        self.assertEqual(self.public()["profile_version"], 13)
        self.assertTrue(all(r["battle_admission"] is False for r in self.public()["inventory"]))
        self.assertEqual(self.public()["resources"], self.source.profile["resources"])

    def test_activation_failpoints_leave_predecessor_schema_and_profile_untouched(self):
        before = self.state()
        with ResearchStore(self.database, self.catalog) as previous_store:
            revision = previous_store.read_profile(self.account)["revision"]
        for point in ("after_battle_schema", "before_battle_activation_commit"):
            self.store.failpoint = point
            self.reject("INJECTED_FAILURE", lambda: self.store.activate(account_id=self.account, authenticated_account_id=self.account))
            self.assertEqual(self.state(), before)
            with ResearchStore(self.database, self.catalog) as previous_store:
                self.assertEqual(previous_store.read_profile(self.account)["revision"], revision)
        self.store.failpoint = None
        self.store.activate(account_id=self.account, authenticated_account_id=self.account)
        self.assertEqual(self.profile()["revision"], revision)

    def test_actual_owned_loadout_reservation_and_restart_replay(self):
        before = self.profile(); request, result = self.start()
        self.assertEqual(result["status"], "admitted")
        frozen = result["reservation"]["frozen"]
        self.assertEqual((frozen["kind"], frozen["descriptor_hex"], frozen["ap_count"], len(frozen["crew_ids"])),
            ("ms1", "010d1a000e00c90000001700170000", 20, 2))
        after = self.profile()
        for key in ("crew_inventory", "ammunition", "depot", "research"): self.assertEqual(before[key], after[key])
        self.assertEqual(next(r for r in after["vehicles"] if r["vehicle_id"] == frozen["vehicle_inventory_id"])["battle_id"], self.run + ":1")
        self.reopen(); snapshot = self.state()
        self.assertEqual(self.store.battle(request, authenticated_account_id=self.account), dict(result, replayed=True))
        self.assertEqual(self.state(), snapshot)
        self.reject("DUPLICATE_PAYLOAD_MISMATCH", lambda: self.store.battle(dict(request, native_inventory_id=2), authenticated_account_id=self.account))

    def test_finish_consumes_owned_AP_once_and_records_actual_damage_free_repair(self):
        before = self.public(); request, result = self.start()
        finish = self.finish_request(result)
        response = self.store.battle(finish, authenticated_account_id=self.account)
        journal = response["reservation"]["result"]
        self.assertEqual(journal, dict(reason="manual_leave", remaining_ap=17, consumed_ap=3, terminal_hp=23,
            destroyed=False, repaired_hp=90, credits=0, xp=0))
        self.assertEqual(self.profile()["ammunition"][0]["loaded"]["shell:ms1-stock-ap"], 17)
        self.assertEqual(self.store.layouts(self.account)[1][1], 17)
        self.assertTrue(all(r["state"] == "available" and r["battle_id"] is None for r in self.profile()["vehicles"]))
        self.assertEqual(self.public()["resources"], before["resources"])
        self.assertEqual(self.public()["inventory"][0]["health"], 90)
        self.reopen(); snapshot = self.state()
        self.assertEqual(self.store.battle(finish, authenticated_account_id=self.account), dict(response, replayed=True))
        self.assertEqual(self.state(), snapshot)
        self.reject("RESERVATION_TERMINAL", lambda: self.store.battle(request, authenticated_account_id=self.account))

    def test_crash_abort_refunds_original_ap_fences_old_jobs_and_is_idempotent(self):
        request, admitted = self.start(); old = self.run
        self.reopen(); self.run = str(uuid.uuid4())
        opened = self.request("run_open")
        response = self.store.battle(opened, authenticated_account_id=self.account)
        result = response["reservation"]["result"]
        self.assertEqual(response["reservation"]["status"], "aborted_restart")
        self.assertEqual(result, dict(reason="aborted_restart", remaining_ap=20, consumed_ap=0,
            terminal_hp=None, destroyed=None, repaired_hp=90, credits=0, xp=0))
        self.assertTrue(all(r["state"] == "available" for r in self.profile()["vehicles"]))
        self.assertEqual(self.profile()["ammunition"][0]["loaded"]["shell:ms1-stock-ap"], 20)
        snapshot = self.state()
        self.assertEqual(self.store.battle(opened, authenticated_account_id=self.account), dict(response, replayed=True))
        self.assertEqual(self.state(), snapshot)
        self.reject("RUN_FENCED", lambda: self.store.battle(request, authenticated_account_id=self.account))
        self.reject("RUN_FENCED", lambda: self.call("run_open", run_id=old))
        self.call("admit", battle_id=self.run + ":1")

    def test_committed_result_survives_next_run_and_no_old_finish_unlocks_new_battle(self):
        request, admitted = self.start()
        finish = self.finish_request(admitted)
        self.store.battle(finish, authenticated_account_id=self.account)
        self.reopen(); self.run = str(uuid.uuid4()); self.call("run_open"); self.call("admit")
        self.reject("RUN_FENCED", lambda: self.store.battle(finish, authenticated_account_id=self.account))
        self.assertEqual(self.profile()["ammunition"][0]["loaded"]["shell:ms1-stock-ap"], 17)
        self.assertEqual(self.store.connection.execute("SELECT count(*) FROM p08b_reservation WHERE status='active'").fetchone()[0], 1)

    def test_unknown_foreign_stale_wrong_battle_and_invalid_results_have_no_writes(self):
        self.call("run_open")
        request = self.request("admit")
        self.reject("FOREIGN_ACCOUNT", lambda: self.store.battle(request, authenticated_account_id="foreign"))
        self.reject("FOREIGN_ACCOUNT", lambda: self.store.battle(dict(request, native_database_id=self.native_id + 1), authenticated_account_id=self.account))
        self.reject("STALE_REVISION", lambda: self.call("admit", expected_revision=1))
        self.reject("UNKNOWN_VEHICLE", lambda: self.call("admit", native_inventory_id=999))
        admitted = self.store.battle(request, authenticated_account_id=self.account)
        self.reject("VEHICLE_RESERVED", lambda: self.call("admit", battle_id=self.run + ":2", native_inventory_id=2))
        finish = self.finish_request(admitted)
        for field, value, code in (("remaining_ap", 21, "INVALID_RESULT"), ("terminal_hp", 91, "INVALID_RESULT"),
            ("battle_id", self.run + ":2", "RESERVATION_MISMATCH"), ("reservation_id", "unknown", "RESERVATION_MISMATCH")):
            self.reject(code, lambda f=field, v=value: self.store.battle(dict(finish, **{f: v}), authenticated_account_id=self.account))

    def test_profile_reserved_blocks_all_existing_hangar_mutations_with_normal_rejection(self):
        _, admitted = self.start()
        revision = self.profile()["revision"]
        request = dict(account_id=self.account, native_database_id=self.native_id, command_key="research-locked",
            expected_revision=revision, wire_revision=1, command=201, arguments=[3329, 0, 0])
        before = self.state()
        result = native_service(self.store, request, authenticated_account_id=self.account)
        self.assertEqual((result["status"], result["result_code"]), ("rejected", -10))
        self.assertEqual(self.state(), before)
        transfer = dict(account_id=self.account, native_database_id=self.native_id, command_key="transfer-locked",
            expected_revision=revision, wire_revision=1, layout=[3, 1, -1])
        result = existing_service(self.store, "transfer", transfer, authenticated_account_id=self.account)
        self.assertEqual((result["status"], result["result_code"]), ("rejected", -10)); self.assertEqual(self.state(), before)
        ammo = dict(account_id=self.account, native_database_id=self.native_id, command_key="ammo-locked",
            expected_revision=revision, wire_revision=1, layout=[5, 1, 6, 2570, 19, 2826, 0, 3082, 0, 6, 0, 0, 0, 0, 0, 0])
        result = existing_service(self.store, "service", ammo, authenticated_account_id=self.account)
        self.assertEqual((result["status"], result["result_code"]), ("rejected", -10)); self.assertEqual(self.state(), before)

    def test_reserved_projection_real_locks_counter_and_companion_preserve_crew_ammo(self):
        _, admitted = self.start()
        aggregate = self.profile(); layouts = self.store.layouts(self.account)
        projected = self.battle_source.state(aggregate, layouts)
        self.assertEqual(projected["inventory"][1]["lock"], {1: 1})
        self.assertEqual(projected["stats"]["battlesTillCaptcha"], 1)
        self.assertEqual(projected["inventory"][1]["shells"][1], [2570, 20, 2826, 0, 3082, 0])
        ordinary = ResearchProjectionSource(os.environ["P04D_TEST_BUNDLE"], self.catalog)
        with self.assertRaises(ValueError): ordinary.state(aggregate, layouts)
        published = self.store.publish(self.battle_source, self.account, Path(self.temp.name) / "fixtures")
        companion = json.loads((Path(published["fixture_dir"]) / "p08b-battle.json").read_text())
        self.assertEqual(companion["policy_sha256"], POLICY_SHA256)
        self.assertIn("p08b-v1", published["fixture_dir"])
        self.assertFalse(companion["capabilities"][0]["admission"])
        self.assertEqual(companion["capabilities"][0]["code"], "VEHICLE_RESERVED")

    def test_unsupported_mount_crew_shells_and_empty_ammo_reject_explicitly(self):
        original = self.profile()
        for expected, change in (
            ("INCOMPLETE_CREW", lambda a: a["crew_inventory"]["members"].clear()),
            ("AMMUNITION_UNSUPPORTED", lambda a: a["ammunition"][0]["loaded"].update({"shell:ms1-stock-he": 1})),
            ("AMMUNITION_EMPTY", lambda a: a["ammunition"][0]["loaded"].update({"shell:ms1-stock-ap": 0})),
            ("BATTLE_PROFILE_UNSUPPORTED", lambda a: a["research"]["vehicles"][0]["modules"].update(engine="module:ussr:engine:GAZ-M1"))):
            value = deepcopy(original); change(value)
            with self.assertRaises(TransactionError) as caught: freeze_loadout(self.catalog, value, 1)
            self.assertEqual(caught.exception.code, expected)
        self.assertEqual(self.profile(), original)

    def test_admit_and_finish_each_failpoint_rolls_back_every_table(self):
        self.call("run_open")
        admit = self.request("admit")
        for point in ("after_battle_vehicle", "after_battle_reservation", "after_snapshot_update", "after_profile_projection", "after_battle_ledger", "before_battle_commit"):
            self.store.failpoint = point
            self.reject("INJECTED_FAILURE", lambda: self.store.battle(admit, authenticated_account_id=self.account))
        self.store.failpoint = None
        result = self.store.battle(admit, authenticated_account_id=self.account)
        finish = self.finish_request(result)
        for point in ("after_battle_result", "after_snapshot_update", "after_profile_projection", "after_battle_ledger", "before_battle_commit"):
            self.store.failpoint = point
            self.reject("INJECTED_FAILURE", lambda: self.store.battle(finish, authenticated_account_id=self.account))
        self.store.failpoint = None
        self.store.battle(finish, authenticated_account_id=self.account)

    def test_restart_recovery_failpoints_leave_prior_reservation_whole(self):
        self.start(); self.run = str(uuid.uuid4()); request = self.request("run_open")
        for point in ("after_battle_result", "after_battle_run", "after_snapshot_update", "after_profile_projection", "after_battle_ledger", "before_battle_commit"):
            self.store.failpoint = point
            self.reject("INJECTED_FAILURE", lambda: self.store.battle(request, authenticated_account_id=self.account))
        self.store.failpoint = None; self.store.battle(request, authenticated_account_id=self.account)

    def test_two_real_connections_cannot_reserve_same_account_twice(self):
        self.call("run_open"); request = self.request("admit"); barrier = threading.Barrier(2)
        def attempt(index):
            with BattleStore(self.database, self.catalog) as store:
                barrier.wait()
                try: return store.battle(dict(request, command_key="race:" + str(index)), authenticated_account_id=self.account)["status"]
                except TransactionError as error: return error.code
        with ThreadPoolExecutor(max_workers=2) as pool: values = list(pool.map(attempt, (1, 2)))
        self.assertEqual(sorted(values), ["STALE_REVISION", "admitted"])
        self.assertEqual(self.store.connection.execute("SELECT count(*) FROM p08b_reservation").fetchone()[0], 1)

    def test_rehashed_poisoned_terminal_frozen_or_response_is_not_replayed(self):
        _, admitted = self.start(); finish = self.finish_request(admitted)
        self.store.battle(finish, authenticated_account_id=self.account)
        c = self.store.connection
        row = c.execute("SELECT * FROM p08b_reservation").fetchone()
        frozen = json.loads(row["frozen_json"]); frozen["max_hp"] = 91; raw = canonical(frozen).decode()
        c.execute("UPDATE p08b_reservation SET frozen_json=?,frozen_sha256=?", (raw, sha(raw.encode()))); c.commit()
        self.reject("CORRUPT_STORE", lambda: self.store.battle(finish, authenticated_account_id=self.account))

    def test_malformed_bounded_requests_and_domain_rejection_reply(self):
        self.call("run_open"); request = self.request("admit")
        for changes in ({"version": True}, {"expected_revision": True}, {"run_id": self.run.upper()},
            {"battle_id": self.run + ":01"}, {"battle_id": self.run + ":18446744073709551616"},
            {"native_inventory_id": True}, {"command_key": "bad space"}, {"operation": []}, {"extra": 1}):
            self.reject("INVALID_INPUT", lambda d=changes: self.store.battle(dict(request, **d), authenticated_account_id=self.account))
        before = self.state()
        reply = battle_service(self.store, dict(request, native_inventory_id=999), authenticated_account_id=self.account)
        self.assertEqual((reply["status"], reply["code"], reply["reservation"]), ("rejected", "UNKNOWN_VEHICLE", None))
        self.assertEqual(self.state(), before)

    def test_real_is7_complete_crew_APonly_and_explicit_loaded_APCR_denial(self):
        for seat in range(5):
            self.store.recruit(dict(account_id=self.account, native_database_id=self.native_id,
                command_key="is7-crew:" + str(seat), expected_revision=self.profile()["revision"], wire_revision=1,
                layout=[3, 2, seat, 0]), authenticated_account_id=self.account)
        def load(ap, premium):
            self.store.service(dict(account_id=self.account, native_database_id=self.native_id,
                command_key="is7-ammo:" + str(self.profile()["revision"]), expected_revision=self.profile()["revision"], wire_revision=1,
                layout=[5, 2, 6, 14602, ap, 14858, premium, 15114, 0, 6, 0, 0, 0, 0, 0, 0]), authenticated_account_id=self.account)
        load(19, 1); self.call("run_open")
        self.reject("AMMUNITION_UNSUPPORTED", lambda: self.call("admit", native_inventory_id=2))
        load(30, 0)
        admitted = self.call("admit", native_inventory_id=2)
        frozen = admitted["reservation"]["frozen"]
        self.assertEqual((frozen["kind"], frozen["descriptor_hex"], frozen["ap_count"], frozen["max_hp"], len(frozen["crew_ids"])),
            ("is7", "011c3a002400cd000b002f003a0000", 30, 2150, 5))
        result = self.call("finish", native_inventory_id=2, reservation_id=admitted["reservation"]["reservation_id"],
            remaining_ap=0, terminal_hp=0, reason="battle_failure")
        self.assertTrue(result["reservation"]["result"]["destroyed"])
        self.assertEqual(self.public()["inventory"][1]["health"], 2150)
        self.assertEqual(self.profile()["ammunition"][1]["loaded"]["shell:is7-stock-ap"], 0)

    def test_canonical_real_writer_vectors(self):
        vectors = []
        def run(operation, **changes):
            request = self.request(operation, **changes)
            result = battle_service(self.store, request, authenticated_account_id=self.account)
            vectors.append({"request": request, "response": result})
            return result
        run("inspect", expected_revision=0)
        run("run_open"); admitted = run("admit"); run("inspect", expected_revision=0)
        run("finish", reservation_id=admitted["reservation"]["reservation_id"], remaining_ap=17, terminal_hp=23, reason="manual_leave")
        run("admit", battle_id=self.run + ":2"); self.run = str(uuid.uuid4())
        run("inspect", expected_revision=0); run("run_open")
        self.assertEqual(vectors[-1]["response"]["reservation"]["status"], "aborted_restart")
        self.assertTrue(all(len(canonical(v["response"])) <= 8192 for v in vectors))
        if os.environ.get("P08B_TEST_VECTORS"):
            path = Path(os.environ["P08B_TEST_VECTORS"])
            self.assertTrue(path.resolve().is_relative_to((ROOT / "local").resolve()))
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("xb") as stream: stream.write(canonical({"version": 1, "vectors": vectors}) + b"\n")

    def test_real_CLI_battle_and_fixture_reopen_same_writer(self):
        self.call("run_open")
        request = self.request("admit")
        prefix = [sys.executable, "-B", "-X", "utf8", str(ROOT / "tools/p08b_battle_service.py"),
            "--database", str(self.database), "--bundle", os.environ["P04D_TEST_BUNDLE"], "--original-root", str(self.original),
            "--account-id", self.account, "--fixture-root", str(Path(self.temp.name) / "fixtures")]
        process = subprocess.run(prefix + ["battle"], input=canonical(request), capture_output=True, timeout=20)
        self.assertEqual(process.returncode, 0, process.stderr.decode())
        result = json.loads(process.stdout)
        self.assertEqual(result["status"], "admitted")
        again = subprocess.run(prefix + ["battle"], input=canonical(request), capture_output=True, timeout=20)
        self.assertEqual(again.returncode, 0, again.stderr.decode())
        self.assertEqual(json.loads(again.stdout), dict(result, replayed=True))
        fixture = subprocess.run(prefix + ["fixture"], capture_output=True, timeout=20)
        self.assertEqual(fixture.returncode, 0, fixture.stderr.decode())
        directory = Path(json.loads(fixture.stdout)["fixture_dir"])
        self.assertTrue((directory / "p08b-battle.json").is_file())


if __name__ == "__main__": unittest.main()
