"""Actual isolated SQLite lineage; gateway final snapshots are authored facts."""
from copy import deepcopy
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
STAGE = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(STAGE / "tools"), str(ROOT / "tools"), str(ROOT)]
from p08c_late_results import (LateResults, LateResultsStore, LossLateResultsStore, CONTRACT, POLICY_NAME,
    canonical, service, vehicle_id, POLICY_SHA256)
from p09e_research_catalog import load_catalog
from p04m_stock_registry import DEFINITION_SHA256
from game_profile_tx import TransactionError

SEED = ROOT / "local/evidence/20261016-p06t-owned01/seed01/seed.json"
RUN = "a7b84ae0-cc3d-4f5d-8df7-3e36e607ed2a"
ARENA = "9007199254740993"
ACCOUNTS = ["c5326cc1-8524-479c-8bba-72e973489c22", "271022a3-41e0-406e-b6fa-59930c320442"]


class Scenario:
    def __init__(self, catalog, loss=False):
        self.temp = tempfile.TemporaryDirectory(prefix="wot091-late-append-")
        self.database = Path(self.temp.name) / "game.sqlite"
        self.seed = json.loads(SEED.read_bytes()); self.catalog = catalog; self.loss = loss; self.serial = 0; self.vectors = []; self.battle_vectors = []; self.arena = ARENA
        with closing(sqlite3.connect(Path(self.seed["database"]).resolve().as_uri() + "?mode=ro", uri=True)) as old, closing(sqlite3.connect(self.database)) as new:
            old.backup(new)
        self.stores = [self.factory(account) for account in ACCOUNTS]
        for account, store in zip(ACCOUNTS, self.stores):
            if not store.pool_active():
                store.activate_pool(dict(version=1, account_id=account, native_database_id=self.public(store)["native_database_id"],
                    command_key="late:pool", expected_revision=store.read_profile(account)["revision"], definition_sha256=DEFINITION_SHA256,
                    registry_sha256=store.registry.sha256), authenticated_account_id=account)
            if not store.mixed_active(): store.activate_mixed(account_id=account, authenticated_account_id=account)
            if loss: store.activate_loss(account_id=account, authenticated_account_id=account,
                native_database_id=self.public(store)["native_database_id"], expected_revision=store.read_profile(account)["revision"])
        self.receipts = []
        for i in range(2):
            self.battle(i, "run_open"); self.receipts.append(self.battle(i, "admit")["reservation"])

    def factory(self, account):
        cls = LossLateResultsStore if self.loss else LateResultsStore
        return cls(self.database, self.catalog, account_id=account, shell_catalog=ROOT / "tests/fixtures/p06t-shell-catalog.json",
            terminal_policy=ROOT / "tests/fixtures/p06t-device-policy.json")

    def close(self):
        for store in self.stores: store.close()
        self.temp.cleanup()

    @staticmethod
    def public(store):
        return json.loads(store.connection.execute("SELECT profile_json FROM game_profiles WHERE account_id=?", (store.pool_account,)).fetchone()[0])

    def battle(self, slot, operation, **fields):
        store = self.stores[slot]; self.serial += 1; account = ACCOUNTS[slot]
        request = dict(version=4 if self.loss else 2, operation=operation, account_id=account, native_database_id=self.public(store)["native_database_id"],
            command_key="late:battle:" + str(self.serial), expected_revision=store.read_profile(account)["revision"], run_id=RUN)
        if self.loss: request["contract"] = "p06t-ammo-rack-loss.v1"
        if operation in ("admit", "finish"): request.update(battle_id=RUN + ":" + self.arena, native_inventory_id=1)
        request.update(fields)
        response = store.battle(request, authenticated_account_id=account)
        self.battle_vectors.append(dict(request=deepcopy(request), response=deepcopy(response)))
        return response

    def frozen(self, slot):
        row = self.receipts[slot]["frozen"]
        return row["loadout"] if self.loss else row

    def final(self, slot, hp=90):
        frozen = self.frozen(slot); source = self.stores[slot].terminal_policy.document["profiles"][frozen["kind"]]
        state = dict(policy_revision=self.stores[slot].terminal_policy.document["policy_revision"], roster_size=2, crew_active=True,
            crew=[dict(crew_id=identity, alive=True) for identity in frozen["crew_ids"]],
            devices=[dict(row, health=row["max_health"]) for row in source["devices"]], fire=dict(active=False, ticks=0, damage=0),
            death=dict(reason=-1, killer_slot=None, tick=0))
        ammo = [dict(shell_compact_id=row["shell_compact_id"], count=row["count"]) for row in frozen["ammunition"]]
        zeros = [dict(row, count=0) for row in ammo]
        return dict(terminal_hp=hp, terminal_state=state, remaining_ammunition=ammo, fired_ammunition=zeros, lost_ammunition=deepcopy(zeros), loss_event=None)

    def result(self, finals):
        participants = []
        for slot, final in enumerate(finals):
            public = self.public(self.stores[slot])
            participants.append(dict(vehicle_id=vehicle_id(slot), account_dbid=public["native_database_id"], name=public["username"], team=slot + 1,
                type_compact_descr=3329, health=final["terminal_hp"], shots=sum(row["count"] for row in final["fired_ammunition"]),
                direct_hits=0, piercings=0, damage_dealt=0, damage_received=90-final["terminal_hp"], kills=0, capture_points=0,
                dropped_capture_points=0, mileage_metres=0, life_time=0, killer_id=0, death_reason=-1, premature_leave=slot == 0))
        return dict(arena_id=int(self.arena), arena_type_id=4, created_unix=1792080000, winner_team=2, finish_reason=5,
            duration_seconds=0, participants=participants)

    def finish(self, slot, final, natural=None):
        value = dict(reservation_id=self.receipts[slot]["reservation_id"], remaining_ammunition=final["remaining_ammunition"],
            terminal_hp=final["terminal_hp"], terminal_state_json=canonical(final["terminal_state"]).decode("utf8"), reason="manual_leave" if natural is None else "battle_finished")
        if self.loss: value.update(fired_ammunition=final["fired_ammunition"], lost_ammunition=final["lost_ammunition"], loss_event=final["loss_event"])
        if natural is not None: value["results_json"] = canonical(natural).decode("utf8")
        return self.battle(slot, "finish", **value)

    def stamp_request(self, slot=0):
        self.serial += 1; store = self.stores[slot]; r = self.receipts[slot]
        return dict(version=1, contract=CONTRACT, operation="release_stamp", account_id=ACCOUNTS[slot],
            native_database_id=self.public(store)["native_database_id"], command_key="late:stamp:" + str(self.serial), run_id=RUN,
            battle_id=RUN + ":" + self.arena, arena_id=self.arena, native_inventory_id=1, reservation_id=r["reservation_id"],
            source_contract="loss-v1" if self.loss else "mixed-v2", frozen_sha256=r["frozen_sha256"])

    def call(self, request):
        store = self.stores[ACCOUNTS.index(request["account_id"])]
        response = service(store, request, authenticated_account_id=request["account_id"])
        self.vectors.append(dict(request=deepcopy(request), response=deepcopy(response)))
        return response

    def append_request(self, finals, result=None, slot=0):
        request = self.stamp_request(slot); stamp = self.call(request)["release_stamp"]
        if stamp is None: raise AssertionError("real finished source required")
        actors = []
        for index in range(2):
            r = self.receipts[index]
            actors.append(dict(account_id=ACCOUNTS[index], native_database_id=self.public(self.stores[index])["native_database_id"], slot=index,
                vehicle_id=vehicle_id(index), team=index+1, reservation_id=r["reservation_id"], native_inventory_id=1,
                source_contract="loss-v1" if self.loss else "mixed-v2", frozen_sha256=r["frozen_sha256"], final_actor=deepcopy(finals[index])))
        seal = dict(version=1, policy=POLICY_NAME, run_id=RUN, battle_id=RUN + ":" + self.arena, arena_id=self.arena,
            results_json=canonical(result or self.result(finals)).decode("utf8"), actors=actors)
        request.update(operation="append", command_key="late:append:" + str(self.serial), release_terminal_sha256=stamp["release_terminal_sha256"],
            finished_revision=stamp["finished_revision"], seal_json=canonical(seal).decode("utf8"))
        return request

    def old_tables(self):
        c = self.stores[0].connection
        return {r[0]: [tuple(v) for v in c.execute('SELECT * FROM "' + r[0] + '"')] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'p08c_late_%'")}

    def query(self, operation="query"):
        self.serial += 1
        request = dict(version=4 if self.loss else 2, operation=operation, account_id=ACCOUNTS[0], native_database_id=self.public(self.stores[0])["native_database_id"],
            command_key="late:result:" + str(self.serial), arena_id=self.arena)
        if self.loss: request["contract"] = "p06t-ammo-rack-loss.v1"
        method = self.stores[0].results_loss if self.loss else self.stores[0].results_mixed
        return request, method(request, authenticated_account_id=ACCOUNTS[0])


class LateResultTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.seed = json.loads(SEED.read_bytes()); cls.catalog = load_catalog(cls.seed["original"])

    def fixture(self, loss=False):
        value = Scenario(self.catalog, loss); self.addCleanup(value.close); return value

    def test_actual_v2_and_loss4_append_read_ack_replay_preserve_every_old_row(self):
        for loss in (False, True):
            with self.subTest(loss=loss):
                f = self.fixture(loss); finals = [f.final(0), f.final(1)]; result = f.result(finals)
                f.finish(0, finals[0]); f.finish(1, finals[1], result); request = f.append_request(finals, result)
                before = f.old_tables(); reply = f.call(request)
                self.assertEqual(reply["status"], "appended"); self.assertEqual(f.old_tables(), before)
                self.assertEqual(f.call(request), dict(reply, replayed=True)); self.assertEqual(f.old_tables(), before)
                adapter = LateResults(f.stores[0]); self.assertEqual(len(adapter.pending(ACCOUNTS[0], 1)), 1)
                _, found = f.query(); self.assertEqual(found["status"], "found"); self.assertEqual(json.loads(found["results_json"]), result)
                ack, acked = f.query("ack"); self.assertTrue(acked["acked"])
                method = f.stores[0].results_loss if loss else f.stores[0].results_mixed
                self.assertTrue(method(ack, authenticated_account_id=ACCOUNTS[0])["replayed"])
                self.assertEqual(adapter.pending(ACCOUNTS[0], 1), []); self.assertEqual(f.old_tables(), before)

    def test_release_stamp_is_readonly_pending_refuses_and_actual_hash_matches_sql(self):
        f = self.fixture(True); before = list(f.stores[0].connection.iterdump()); request = f.stamp_request()
        self.assertEqual(f.call(request)["code"], "RELEASE_NOT_READY"); self.assertEqual(list(f.stores[0].connection.iterdump()), before)
        f.finish(0, f.final(0)); before = list(f.stores[0].connection.iterdump()); reply = f.call(request)
        row = f.stores[0].connection.execute("SELECT result_sha256 FROM battle_ammo_loss_reservation WHERE account_id=? AND reservation_id=?", (ACCOUNTS[0], f.receipts[0]["reservation_id"])).fetchone()
        self.assertEqual(reply["release_stamp"]["release_terminal_sha256"], row[0]); self.assertEqual(list(f.stores[0].connection.iterdump()), before)
        self.assertFalse(any("p08c_late_" in line for line in before)); self.assertEqual(f.stores[0].connection.execute("PRAGMA query_only").fetchone()[0], 0)

    def test_changed_parked_hp_or_device_or_ammo_refuses_without_side_effects(self):
        f = self.fixture(True); original = [f.final(0), f.final(1)]; f.finish(0, original[0]); before = list(f.stores[0].connection.iterdump())
        for change in ("hp", "device", "ammo"):
            finals = deepcopy(original)
            if change == "hp": finals[0]["terminal_hp"] = 89
            elif change == "device": finals[0]["terminal_state"]["devices"][0]["health"] -= 1
            else:
                stack = next(i for i, row in enumerate(finals[0]["remaining_ammunition"]) if row["count"] > 0)
                finals[0]["remaining_ammunition"][stack]["count"] -= 1
                finals[0]["fired_ammunition"][stack]["count"] += 1
            request = f.append_request(finals); reply = f.call(request)
            self.assertEqual(reply["code"], "LATE_ACTOR_STATE_CHANGED", change); self.assertEqual(list(f.stores[0].connection.iterdump()), before)

    def test_source_hash_owner_native_and_result_poison_are_atomic(self):
        f = self.fixture(); finals = [f.final(0), f.final(1)]; f.finish(0, finals[0]); request = f.append_request(finals)
        before = list(f.stores[0].connection.iterdump())
        for changes in ({"release_terminal_sha256": "0"*64}, {"finished_revision": request["finished_revision"]+1}, {"frozen_sha256": "0"*64}, {"native_database_id": 2}):
            result = f.call(dict(request, **changes)); self.assertIn(result["code"], ("RESULT_MISMATCH", "FOREIGN_ACCOUNT")); self.assertEqual(list(f.stores[0].connection.iterdump()), before)

    def test_append_and_ack_failpoints_rollback_whole_namespace(self):
        f = self.fixture(True); finals = [f.final(0), f.final(1)]; f.finish(0, finals[0]); request = f.append_request(finals)
        for point in ("after_late_seal", "after_late_result_notice", "before_late_append_commit"):
            before = list(f.stores[0].connection.iterdump()); f.stores[0].failpoint = point
            with self.assertRaises(TransactionError): f.call(request)
            self.assertEqual(list(f.stores[0].connection.iterdump()), before)
        f.stores[0].failpoint = None; self.assertEqual(f.call(request)["status"], "appended")
        before = list(f.stores[0].connection.iterdump()); f.stores[0].failpoint = "before_late_ack_commit"
        with self.assertRaises(TransactionError): f.query("ack")
        self.assertEqual(list(f.stores[0].connection.iterdump()), before)

    def test_actual_natural_existing_row_is_verified_not_duplicated(self):
        f = self.fixture(True); finals = [f.final(0), f.final(1)]; result = f.result(finals)
        f.finish(0, finals[0]); f.finish(1, finals[1], result); request = f.append_request(finals, result, slot=1)
        before = f.old_tables(); self.assertEqual(f.call(request)["status"], "already_present"); self.assertEqual(f.old_tables(), before)
        self.assertEqual(f.stores[1].connection.execute("SELECT count(*) FROM p08c_late_result").fetchone()[0], 0)

    def test_release_read_transaction_sees_coherent_active_before_concurrent_actual_finish(self):
        f = self.fixture(True); second = f.factory(ACCOUNTS[0]); self.addCleanup(second.close)
        adapter = LateResults(f.stores[0]); original_native = adapter.native; finished = []
        def native_then_finish(account, native):
            original_native(account, native)  # This actual SELECT starts the read snapshot.
            if not finished:
                first = f.stores[0]; f.stores[0] = second
                try: finished.append(f.finish(0, f.final(0)))
                finally: f.stores[0] = first
        adapter.native = native_then_finish
        with self.assertRaises(TransactionError) as caught:
            adapter.release_stamp(f.stamp_request(), ACCOUNTS[0])
        self.assertEqual(caught.exception.code, "RELEASE_NOT_READY")
        self.assertEqual(finished[0]["status"], "finished")
        self.assertEqual(f.call(f.stamp_request())["status"], "stamped")
        self.assertEqual(f.stores[0].connection.execute("PRAGMA query_only").fetchone()[0], 0)
        self.assertFalse(LateResults(f.stores[0]).namespace())

    def test_reopen_old_run_known_seal_is_readable_and_reconciles_without_inventory_reopen(self):
        f = self.fixture(True); finals = [f.final(0), f.final(1)]; f.finish(0, finals[0]); f.finish(1, finals[1], f.result(finals))
        request = f.append_request(finals); self.assertEqual(f.call(request)["status"], "appended")
        old = f.stores[0]; old.close(); f.stores[0] = f.factory(ACCOUNTS[0])
        self.assertEqual(f.call(request)["status"], "appended"); self.assertTrue(f.call(request)["replayed"])
        f.battle(0, "run_open", run_id="24b61fb1-03f4-468c-bbe6-5466c07cbe18")
        self.assertEqual(f.query()[1]["status"], "found")
        self.assertEqual(f.call(dict(request, command_key="late:known:reconcile"))["status"], "already_present")
        # A different owner has no pre-existing late namespace receipt for this arena,
        # but the common final seal was committed already and can be verified.
        peer = f.append_request(finals, slot=1)
        self.assertEqual(f.call(peer)["status"], "already_present")

    def test_new_unsealed_retired_run_refuses_without_namespace_or_inventory_write(self):
        f = self.fixture(True); finals = [f.final(0), f.final(1)]; f.finish(0, finals[0]); request = f.append_request(finals)
        f.battle(0, "run_open", run_id="24b61fb1-03f4-468c-bbe6-5466c07cbe18")
        before = list(f.stores[0].connection.iterdump())
        self.assertEqual(f.call(request)["code"], "RUN_FENCED")
        self.assertEqual(list(f.stores[0].connection.iterdump()), before)

    def test_other_actor_contract_or_boolean_identity_poison_refuses(self):
        f = self.fixture(True); finals = [f.final(0), f.final(1)]; f.finish(0, finals[0]); original = f.append_request(finals)
        before = list(f.stores[0].connection.iterdump())
        for field, value in (("source_contract", "unknown"), ("native_database_id", True), ("team", True)):
            seal = json.loads(original["seal_json"]); seal["actors"][1][field] = value
            request = dict(original, seal_json=canonical(seal).decode("utf8"))
            reply = f.call(request); self.assertEqual(reply["status"], "rejected"); self.assertEqual(list(f.stores[0].connection.iterdump()), before)

    def test_canonical_utf8_duplicate_keys_and_explicit_byte_bounds(self):
        from p08c_late_results import decode, validate_request
        self.assertEqual(canonical({"имя": "Ёж", "a": 1}), b'{"a":1,"\xd0\xb8\xd0\xbc\xd1\x8f":"\xd0\x81\xd0\xb6"}')
        for raw in ('{"a":1,"a":2}', '[0.5]', '[' * 14 + '0' + ']' * 14):
            with self.assertRaises(TransactionError): decode(raw)
        fixture = json.loads((ROOT / "tests/fixtures/p08c-late-loss-two-owner-vectors.json").read_bytes())
        request = next(v["request"] for v in fixture["append_vectors"] if v["request"]["operation"] == "append")
        with self.assertRaises(TransactionError): validate_request(dict(request, seal_json="я" * 16385), request["account_id"])
        with self.assertRaises(TransactionError): validate_request(dict(request, arena_id="9223372036854775808"), request["account_id"])

    def test_loss_facade_ordinary_ammo_crew_publish_and_old_writer_mode_fences_remain_real(self):
        from p06t_ammo_loss_store import CONTRACT as LOSS_CONTRACT
        from p06t_mixed_store import MixedAmmoStore
        from p08b_owner_source import projection_source
        f = self.fixture(True); finals = [f.final(0), f.final(1)]; f.finish(0, finals[0]); f.finish(1, finals[1], f.result(finals))
        append = f.append_request(finals); self.assertEqual(f.call(append)["status"], "appended")
        store = f.stores[0]; account = ACCOUNTS[0]; native = f.public(store)["native_database_id"]
        peer_before = f.stores[1].read_profile(ACCOUNTS[1]); original = store.read_profile(account); layout = store.layouts(account)[1]
        for number, counts in enumerate(([0, 0, 0], layout[1::2])):
            request = dict(account_id=account, native_database_id=native, command_key="late:ordinary:ammo:" + str(number),
                expected_revision=store.read_profile(account)["revision"], wire_revision=1,
                layout=[5, 1, 6, 2570, counts[0], 2826, counts[1], 3082, counts[2], 6, 0, 0, 0, 0, 0, 0])
            response = store.service(request, authenticated_account_id=account)
            self.assertEqual(response["status"], "serviced")
            self.assertTrue(store.service(request, authenticated_account_id=account)["replayed"])
        self.assertEqual(store.read_profile(account)["ammunition"], original["ammunition"])
        self.assertEqual(store.read_profile(account)["depot"], original["depot"])
        driver = store.connection.execute("SELECT native_id FROM p04d_crew_member WHERE account_id=? AND vehicle_native_id=1 AND seat=1", (account,)).fetchone()[0]
        for number, member in enumerate((-1, driver)):
            request = dict(account_id=account, native_database_id=native, command_key="late:ordinary:crew:" + str(number),
                expected_revision=store.read_profile(account)["revision"], wire_revision=1, layout=[1, 1, member])
            response = store.transfer(request, authenticated_account_id=account)
            self.assertEqual(response["status"], "transferred")
            self.assertTrue(store.transfer(request, authenticated_account_id=account)["replayed"])
        self.assertEqual(f.stores[1].read_profile(ACCOUNTS[1]), peer_before)
        self.assertEqual(f.query()[1]["status"], "found")  # Immutable archive remains readable after real CAS advances.
        source = projection_source(f.seed["bundle"], f.catalog, f.database, account)
        published = store.publish(source, account, Path(f.temp.name) / "ordinary-fixtures")
        self.assertTrue((Path(published["fixture_dir"]) / "p06t-ammo-loss.json").is_file())
        self.assertEqual(store.AMMO_LOSS_CONTRACT, LOSS_CONTRACT)
        old = MixedAmmoStore(f.database, f.catalog, account_id=account, shell_catalog=ROOT / "tests/fixtures/p06t-shell-catalog.json",
            terminal_policy=ROOT / "tests/fixtures/p06t-device-policy.json")
        self.addCleanup(old.close)
        with self.assertRaises(TransactionError) as caught: old.read_profile(account)
        self.assertEqual(caught.exception.code, "AMMO_LOSS_POLICY_REQUIRED")
        old_query = dict(version=2, operation="query", account_id=account, native_database_id=native,
            command_key="late:wrongmode", arena_id=ARENA)
        with self.assertRaises(TransactionError) as caught: store.results_mixed(old_query, authenticated_account_id=account)
        self.assertEqual(caught.exception.code, "AMMO_LOSS_POLICY_REQUIRED")

    def test_new_loss_facade_reads_old_mixed_late_archive_and_old_other_owner_still_works(self):
        from p06t_ammo_loss_store import CONTRACT as LOSS_CONTRACT
        from p06t_mixed_store import MixedAmmoStore
        f = self.fixture(False); finals = [f.final(0), f.final(1)]; f.finish(0, finals[0]); f.finish(1, finals[1], f.result(finals))
        request = f.append_request(finals); f.stores[0].close()
        store = LossLateResultsStore(f.database, f.catalog, account_id=ACCOUNTS[0], shell_catalog=ROOT / "tests/fixtures/p06t-shell-catalog.json",
            terminal_policy=ROOT / "tests/fixtures/p06t-device-policy.json")
        f.stores[0] = store
        store.activate_loss(account_id=ACCOUNTS[0], authenticated_account_id=ACCOUNTS[0],
            expected_revision=store.read_profile(ACCOUNTS[0])["revision"], native_database_id=f.public(store)["native_database_id"])
        before = f.old_tables(); self.assertEqual(f.call(request)["status"], "appended"); self.assertEqual(f.old_tables(), before)
        query = dict(version=4, contract=LOSS_CONTRACT, operation="query", account_id=ACCOUNTS[0],
            native_database_id=f.public(store)["native_database_id"], command_key="late:archive4", arena_id=ARENA)
        self.assertEqual(store.results_loss(query, authenticated_account_id=ACCOUNTS[0])["record_contract"], "mixed-v2")
        with MixedAmmoStore(f.database, f.catalog, account_id=ACCOUNTS[1], shell_catalog=ROOT / "tests/fixtures/p06t-shell-catalog.json",
            terminal_policy=ROOT / "tests/fixtures/p06t-device-policy.json") as old_peer:
            self.assertEqual(old_peer.read_profile(ACCOUNTS[1]), f.stores[1].read_profile(ACCOUNTS[1]))

    def test_ambient_transaction_refuses_without_query_only_change_or_caller_rollback(self):
        f = self.fixture(True); finals = [f.final(0), f.final(1)]; f.finish(0, finals[0]); request = f.append_request(finals)
        adapter = LateResults(f.stores[0]); c = adapter.connection; stamp = f.stamp_request()
        query = dict(version=4, contract="p06t-ammo-rack-loss.v1", operation="query", account_id=ACCOUNTS[0],
            native_database_id=f.public(f.stores[0])["native_database_id"], command_key="late:ambient", arena_id=ARENA)
        actions = [lambda: adapter.release_stamp(stamp, ACCOUNTS[0]), lambda: adapter.append(request, ACCOUNTS[0]),
            lambda: adapter.pending(ACCOUNTS[0], 1), lambda: adapter.results(query, ACCOUNTS[0])]
        for readonly in (0, 1):
            for action in actions:
                before = list(c.iterdump()); c.execute("BEGIN")
                c.execute("INSERT INTO game_meta VALUES ('late_ambient_proof','retained')")
                c.execute("PRAGMA query_only=" + str(readonly))
                with self.assertRaises(TransactionError) as caught: action()
                self.assertEqual(caught.exception.code, "LATE_TRANSACTION_REQUIRED")
                self.assertTrue(c.in_transaction); self.assertEqual(c.execute("PRAGMA query_only").fetchone()[0], readonly)
                self.assertEqual(c.execute("SELECT value FROM game_meta WHERE key='late_ambient_proof'").fetchone()[0], "retained")
                c.rollback(); c.execute("PRAGMA query_only=OFF"); self.assertEqual(list(c.iterdump()), before)

    def test_ack_command_key_is_single_namespace_across_real_late_and_natural_arenas(self):
        f = self.fixture(True); finals = [f.final(0), f.final(1)]; f.finish(0, finals[0]); self.assertEqual(f.call(f.append_request(finals))["status"], "appended")
        store = f.stores[0]; arena2 = str(int(ARENA) + 1)
        admitted = f.battle(0, "admit", battle_id=RUN + ":" + arena2)["reservation"]
        self.assertEqual(admitted["frozen"]["loadout"], f.frozen(0))
        result = f.result(finals); result.update(arena_id=int(arena2), winner_team=1)
        result["participants"][0]["premature_leave"] = False; result["participants"][1]["premature_leave"] = True
        natural = dict(battle_id=RUN + ":" + arena2, reservation_id=admitted["reservation_id"], reason="battle_finished", terminal_hp=90,
            remaining_ammunition=finals[0]["remaining_ammunition"], fired_ammunition=finals[0]["fired_ammunition"],
            lost_ammunition=finals[0]["lost_ammunition"], loss_event=None, terminal_state_json=canonical(finals[0]["terminal_state"]).decode("utf8"),
            results_json=canonical(result).decode("utf8"))
        self.assertEqual(f.battle(0, "finish", **natural)["status"], "finished")
        ack = dict(version=4, contract="p06t-ammo-rack-loss.v1", operation="ack", account_id=ACCOUNTS[0],
            native_database_id=f.public(store)["native_database_id"], command_key="late:cross:late-key", arena_id=ARENA)
        self.assertTrue(store.results_loss(ack, authenticated_account_id=ACCOUNTS[0])["acked"])
        before = list(store.connection.iterdump())
        with self.assertRaises(TransactionError) as caught: store.results_loss(dict(ack, arena_id=arena2), authenticated_account_id=ACCOUNTS[0])
        self.assertEqual(caught.exception.code, "DUPLICATE_PAYLOAD_MISMATCH"); self.assertEqual(list(store.connection.iterdump()), before)
        natural_ack = dict(ack, arena_id=arena2, command_key="late:cross:natural-key")
        self.assertTrue(store.results_loss(natural_ack, authenticated_account_id=ACCOUNTS[0])["acked"])
        before = list(store.connection.iterdump())
        with self.assertRaises(TransactionError) as caught: store.results_loss(dict(natural_ack, arena_id=ARENA), authenticated_account_id=ACCOUNTS[0])
        self.assertEqual(caught.exception.code, "DUPLICATE_PAYLOAD_MISMATCH"); self.assertEqual(list(store.connection.iterdump()), before)
        # The exact new archive branch writes byte-compatible original receipts.
        from p06t_ammo_loss_store import AmmoLossStore
        with AmmoLossStore(f.database, f.catalog, account_id=ACCOUNTS[0], shell_catalog=ROOT / "tests/fixtures/p06t-shell-catalog.json",
            terminal_policy=ROOT / "tests/fixtures/p06t-device-policy.json") as old_loss:
            self.assertTrue(old_loss.results_loss(natural_ack, authenticated_account_id=ACCOUNTS[0])["replayed"])

    def test_pending_actual_nine_arenas_key_pages_do_not_ack_skip_or_expose_peer(self):
        from p08c_late_results import pending_service
        f = self.fixture(True); ids = [ARENA, "2", "11", "20", "3", "31", "4", "41", "5"]
        for index, arena in enumerate(ids):
            if index:
                f.arena = arena
                f.receipts = [f.battle(slot, "admit")["reservation"] for slot in range(2)]
            finals = [f.final(0), f.final(1)]; f.finish(0, finals[0]); f.finish(1, finals[1], f.result(finals))
            self.assertEqual(f.call(f.append_request(finals))["status"], "appended")
        store = f.stores[0]; native = f.public(store)["native_database_id"]
        request = dict(version=1, contract=CONTRACT, operation="pending", account_id=ACCOUNTS[0], native_database_id=native,
            command_key="late:pending:page", after_arena_id=None)
        before = list(store.connection.iterdump()); page = pending_service(store, request, authenticated_account_id=ACCOUNTS[0])
        self.assertEqual([r["arena_id"] for r in page["rows"]], sorted(ids)[:8]); self.assertEqual(page["next_arena_id"], sorted(ids)[7])
        self.assertEqual(page, pending_service(store, request, authenticated_account_id=ACCOUNTS[0]))
        self.assertEqual(list(store.connection.iterdump()), before)
        self.assertTrue(all(r["vehicle_type_compact_id"] == 3329 for r in page["rows"]))
        tail = pending_service(store, dict(request, after_arena_id=page["next_arena_id"]), authenticated_account_id=ACCOUNTS[0])
        self.assertEqual([r["arena_id"] for r in tail["rows"]], sorted(ids)[8:]); self.assertIsNone(tail["next_arena_id"])
        ack = dict(version=4, contract="p06t-ammo-rack-loss.v1", operation="ack", account_id=ACCOUNTS[0], native_database_id=native,
            command_key="late:pending:actual1501", arena_id=page["rows"][0]["arena_id"])
        self.assertTrue(store.results_loss(ack, authenticated_account_id=ACCOUNTS[0])["acked"])
        restarted = pending_service(store, request, authenticated_account_id=ACCOUNTS[0])
        self.assertEqual([r["arena_id"] for r in restarted["rows"]], sorted(ids)[1:]); self.assertIsNone(restarted["next_arena_id"])
        wrong = pending_service(store, dict(request, native_database_id=native+100), authenticated_account_id=ACCOUNTS[0])
        self.assertEqual(wrong["code"], "FOREIGN_ACCOUNT"); self.assertEqual(wrong["rows"], [])
        peer = f.stores[1]; peer_request = dict(request, account_id=ACCOUNTS[1], native_database_id=f.public(peer)["native_database_id"])
        self.assertEqual(pending_service(peer, peer_request, authenticated_account_id=ACCOUNTS[1])["rows"], [])

    def test_committed_owner_result_survives_real_peer_restart_abort_without_inventing_peer_result(self):
        for loss in (False, True):
            with self.subTest(loss=loss):
                f = self.fixture(loss); finals = [f.final(0), f.final(1)]; f.finish(0, finals[0])
                request = f.append_request(finals); self.assertEqual(f.call(request)["status"], "appended")
                a_profile = f.stores[0].read_profile(ACCOUNTS[0])
                a_reservation = tuple(f.stores[0].connection.execute("SELECT * FROM p06t_reservation WHERE account_id=?", (ACCOUNTS[0],)).fetchone())
                b_before = f.stores[1].read_profile(ACCOUNTS[1])["ammunition"]
                aborted = f.battle(1, "run_open", run_id="24b61fb1-03f4-468c-bbe6-5466c07cbe18")
                self.assertEqual(aborted["reservation"]["status"], "aborted_restart")
                self.assertIsNone(aborted["reservation"]["result"]["terminal_hp"])
                self.assertEqual(f.stores[1].read_profile(ACCOUNTS[1])["ammunition"], b_before)
                f.stores[0].close(); f.stores[0] = f.factory(ACCOUNTS[0])
                self.assertEqual(f.query()[1]["status"], "found")
                self.assertEqual(len(LateResults(f.stores[0]).pending(ACCOUNTS[0], f.public(f.stores[0])["native_database_id"])), 1)
                self.assertTrue(f.call(request)["replayed"])
                self.assertTrue(f.query("ack")[1]["acked"])
                self.assertEqual(LateResults(f.stores[0]).pending(ACCOUNTS[0], f.public(f.stores[0])["native_database_id"]), [])
                self.assertEqual(f.stores[0].read_profile(ACCOUNTS[0]), a_profile)
                self.assertEqual(tuple(f.stores[0].connection.execute("SELECT * FROM p06t_reservation WHERE account_id=?", (ACCOUNTS[0],)).fetchone()), a_reservation)
                self.assertEqual(f.call(f.stamp_request(slot=1))["code"], "RELEASE_NOT_READY")
                self.assertEqual(f.stores[1].connection.execute("SELECT count(*) FROM p08c_late_result WHERE account_id=?", (ACCOUNTS[1],)).fetchone()[0], 0)
                self.assertEqual(f.stores[1].connection.execute("SELECT count(*) FROM p06t_result WHERE account_id=?", (ACCOUNTS[1],)).fetchone()[0], 0)


if __name__ == "__main__": unittest.main()
