"""Real SQLite acceptance for the isolated P09C ammunition domain boundary.

These checks do not establish native/runtime integration or historical prices.
Every temporary database lives under this worktree's ignored evidence directory.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from game_profile_tx import GameProfileStore, TransactionError
from p09c_ammo_catalog import CATALOG_SHA256, MOUNTS, SHELLS
from p09c_ammo_service import AmmoServiceStore, MAX_DEPOT, MAX_OWNED, SCHEMA

TEMP_ROOT = ROOT / "local/evidence/20261013-p09c-ammo-service-01/tmp"
MS1 = "inventory-ms1"
IS7 = "inventory-is7"
ACCOUNT = "acct-a"
TABLES = (
    ("p09c_schema", "version"),
    ("game_snapshot", "account_id"),
    ("game_vehicle", "account_id, vehicle_id"),
    ("game_command_ledger", "account_id, command_id"),
    ("p09c_ammo_mount", "account_id, vehicle_id"),
    ("p09c_ammo_depot", "account_id, shell_id"),
)


class AmmoServiceTransactionTests(unittest.TestCase):
    def setUp(self):
        TEMP_ROOT.mkdir(parents=True, exist_ok=True)
        self.tempdir = tempfile.TemporaryDirectory(prefix="test-", dir=TEMP_ROOT)
        self.db = Path(self.tempdir.name) / "profile.sqlite3"
        self.store = AmmoServiceStore(self.db)
        self.store.initialize()
        self.store.create_profile(ACCOUNT, (MS1, IS7))
        self.mounts = {MS1: "ms1-stock", IS7: "is7-stock"}
        self.depot = {shell: 300 for shell in SHELLS}
        self.store.seed_test_ammunition(ACCOUNT, self.mounts, self.depot)
        self.ms_shells = tuple(MOUNTS["ms1-stock"].shell_ids)
        self.is_shells = tuple(MOUNTS["is7-stock"].shell_ids)

    def tearDown(self):
        self.store.close()
        self.tempdir.cleanup()

    def command(self, **overrides):
        values = {
            "authenticated_account_id": ACCOUNT,
            "account_id": ACCOUNT,
            "command_id": "ammo-1",
            "vehicle_id": MS1,
            "expected_revision": 0,
            "desired": {self.ms_shells[0]: 20},
        }
        values.update(overrides)
        return self.store.set_ammunition(**values)

    def profile(self, account=ACCOUNT):
        return self.store.read_profile(account)

    def loaded(self, vehicle_id=MS1, account=ACCOUNT):
        return next(row["loaded"] for row in self.profile(account)["ammunition"]
                    if row["vehicle_id"] == vehicle_id)

    def state(self):
        # Logical rows, including raw snapshot/ledger bytes, establish complete
        # transaction rollback without depending on SQLite file housekeeping.
        return {
            table: [tuple(row) for row in self.store.connection.execute(
                f"SELECT * FROM {table} ORDER BY {order}").fetchall()]
            for table, order in TABLES
        }

    def reject_unchanged(self, code, **overrides):
        before = self.state()
        with self.assertRaises(TransactionError) as raised:
            self.command(**overrides)
        self.assertEqual(raised.exception.code, code)
        self.assertEqual(self.state(), before)
        self.assertFalse(self.store.connection.in_transaction)

    def conservation(self, account=ACCOUNT):
        profile = self.profile(account)
        return {shell: profile["depot"][shell] + sum(
            ammo["loaded"].get(shell, 0) for ammo in profile["ammunition"]
        ) for shell in SHELLS}

    def reopen(self, **kwargs):
        self.store.close()
        self.store = AmmoServiceStore(self.db, **kwargs)
        self.store.initialize()

    def write(self, sql, parameters=()):
        self.store.connection.execute(sql, parameters)
        self.store.connection.commit()

    def test_bootstrap_is_versioned_empty_load_with_owned_depot(self):
        profile = self.profile()
        self.assertEqual(profile["schema"], SCHEMA)
        self.assertEqual(profile["catalog_sha256"], CATALOG_SHA256)
        self.assertEqual(profile["revision"], 0)
        self.assertEqual(profile["depot"], self.depot)
        self.assertEqual(self.loaded(), dict.fromkeys(self.ms_shells, 0))
        self.assertEqual(self.loaded(IS7), dict.fromkeys(self.is_shells, 0))
        self.assertEqual(self.store.ledger_count(ACCOUNT), 0)

    def test_success_moves_owned_stock_and_advances_shared_revision_once(self):
        original = self.conservation()
        result = self.command()
        self.assertEqual(result["status"], "serviced")
        self.assertEqual(result["financial_status"], "UNSUPPORTED")
        self.assertFalse(result["replayed"])
        self.assertEqual((result["source_revision"], result["destination_revision"]), (0, 1))
        self.assertEqual(self.profile()["revision"], 1)
        self.assertEqual(self.store.ledger_count(ACCOUNT), 1)
        self.assertEqual(self.loaded()[self.ms_shells[0]], 20)
        self.assertEqual(self.profile()["depot"][self.ms_shells[0]], 280)
        self.assertEqual(result["depot_delta"][self.ms_shells[0]], -20)
        self.assertEqual(self.conservation(), original)

    def test_each_source_mount_accepts_exact_capacity(self):
        original = self.conservation()
        for revision, (vehicle, mount_id) in enumerate(self.mounts.items()):
            with self.subTest(mount=mount_id):
                mount = MOUNTS[mount_id]
                self.command(vehicle_id=vehicle, command_id=f"capacity-{revision}",
                             expected_revision=revision, desired={mount.shell_ids[0]: mount.capacity})
                self.assertEqual(sum(self.loaded(vehicle).values()), mount.capacity)
        self.assertEqual(self.conservation(), original)

    def test_each_compatible_shell_can_be_selected_without_cross_vehicle_change(self):
        revision = 0
        original = self.conservation()
        for vehicle, mount_id in self.mounts.items():
            for shell in MOUNTS[mount_id].shell_ids:
                with self.subTest(vehicle=vehicle, shell=shell):
                    other = IS7 if vehicle == MS1 else MS1
                    other_before = self.loaded(other)
                    self.command(vehicle_id=vehicle, command_id=f"select-{revision}",
                                 expected_revision=revision, desired={shell: 1})
                    self.assertEqual(self.loaded(vehicle)[shell], 1)
                    self.assertEqual(sum(self.loaded(vehicle).values()), 1)
                    self.assertEqual(self.loaded(other), other_before)
                    self.assertEqual(self.conservation(), original)
                    revision += 1

    def test_absolute_selection_unloads_omitted_shells_and_returns_owned_stock(self):
        original = self.conservation()
        first, second = self.ms_shells[:2]
        self.command(desired={first: 20, second: 10})
        result = self.command(command_id="change", expected_revision=1, desired={second: 25})
        self.assertEqual(self.loaded()[first], 0)
        self.assertEqual(self.loaded()[second], 25)
        self.assertEqual(result["depot_delta"][first], 20)
        self.assertEqual(result["depot_delta"][second], -15)
        self.assertEqual(self.conservation(), original)
        self.command(command_id="unload", expected_revision=2, desired={})
        self.assertEqual(self.loaded(), dict.fromkeys(self.ms_shells, 0))
        self.assertEqual(self.profile()["depot"], self.depot)
        self.assertEqual(self.conservation(), original)

    def test_refill_changes_only_difference_not_entire_desired_count(self):
        self.command(desired={self.ms_shells[0]: 10})
        result = self.command(command_id="refill", expected_revision=1,
                              desired={self.ms_shells[0]: 20})
        self.assertEqual(result["depot_delta"][self.ms_shells[0]], -10)
        self.assertEqual(self.profile()["depot"][self.ms_shells[0]], 280)

    def test_exact_replay_has_no_second_debit_revision_or_ledger_row(self):
        first = self.command()
        before = self.state()
        replay = self.command()
        self.assertEqual(replay, {**first, "replayed": True})
        self.assertEqual(self.state(), before)

    def test_replay_survives_reopen(self):
        first = self.command()
        before = self.state()
        self.reopen()
        self.assertEqual(self.command(), {**first, "replayed": True})
        self.assertEqual(self.state(), before)

    def test_replay_after_later_command_returns_original_without_overwriting_current_load(self):
        first = self.command()
        self.command(command_id="later", expected_revision=1, desired={self.ms_shells[1]: 5})
        before = self.state()
        replay = self.command()
        self.assertEqual(replay, {**first, "replayed": True})
        self.assertEqual(self.state(), before)
        self.assertEqual(self.loaded()[self.ms_shells[1]], 5)

    def test_payload_key_order_does_not_change_replay_identity(self):
        first = self.command(desired={self.ms_shells[0]: 10, self.ms_shells[1]: 5})
        before = self.state()
        replay = self.command(desired={self.ms_shells[1]: 5, self.ms_shells[0]: 10})
        self.assertEqual(replay, {**first, "replayed": True})
        self.assertEqual(self.state(), before)

    def test_changed_command_payload_is_rejected(self):
        self.command()
        for changed in ({"desired": {self.ms_shells[0]: 21}}, {"expected_revision": 1},
                        {"vehicle_id": IS7, "desired": {self.is_shells[0]: 1}}):
            with self.subTest(changed=changed):
                self.reject_unchanged("DUPLICATE_PAYLOAD_MISMATCH", **changed)

    def test_foreign_account_is_rejected_before_existing_command_replay(self):
        self.command()
        self.reject_unchanged("FOREIGN_ACCOUNT", authenticated_account_id="acct-b")

    def test_foreign_account_new_command_and_foreign_vehicle_are_rejected(self):
        self.store.create_profile("acct-b", ("foreign-ms1",))
        self.store.seed_test_ammunition("acct-b", {"foreign-ms1": "ms1-stock"}, self.depot)
        self.reject_unchanged("FOREIGN_ACCOUNT", account_id="acct-b", vehicle_id="foreign-ms1")
        self.reject_unchanged("UNKNOWN_VEHICLE", vehicle_id="foreign-ms1")

    def test_unknown_account_and_vehicle_fail_without_changes(self):
        self.reject_unchanged("UNKNOWN_ACCOUNT", authenticated_account_id="missing", account_id="missing")
        self.reject_unchanged("UNKNOWN_VEHICLE", vehicle_id="missing")

    def test_stale_revision_is_rejected_after_another_vehicle_changes(self):
        self.command(vehicle_id=IS7, desired={self.is_shells[0]: 1})
        self.reject_unchanged("STALE_REVISION", command_id="stale")

    def test_reserved_vehicle_rejects_service_and_preserves_ammunition(self):
        self.command()
        ammo_before = self.profile()["ammunition"]
        depot_before = self.profile()["depot"]
        self.store.reserve_vehicle(account_id=ACCOUNT, command_id="reserve", vehicle_id=MS1,
                                   expected_revision=1, battle_id="battle-a")
        self.assertEqual(self.profile()["revision"], 2)
        self.assertEqual(self.profile()["ammunition"], ammo_before)
        self.assertEqual(self.profile()["depot"], depot_before)
        self.assertEqual(self.store.ledger_count(ACCOUNT), 2)
        self.reject_unchanged("VEHICLE_RESERVED", command_id="reserved", expected_revision=2)

    def test_other_available_vehicle_can_be_serviced_after_reservation(self):
        self.store.reserve_vehicle(account_id=ACCOUNT, command_id="reserve", vehicle_id=MS1,
                                   expected_revision=0, battle_id="battle-a")
        self.command(expected_revision=1, vehicle_id=IS7, desired={self.is_shells[0]: 2})
        self.assertEqual(self.profile()["revision"], 2)
        self.assertEqual(self.loaded(IS7)[self.is_shells[0]], 2)

    def test_shared_command_namespace_rejects_reservation_then_ammo_collision(self):
        self.store.reserve_vehicle(account_id=ACCOUNT, command_id="ammo-1", vehicle_id=IS7,
                                   expected_revision=0, battle_id="battle-a")
        self.reject_unchanged("DUPLICATE_PAYLOAD_MISMATCH")

    def test_shared_command_namespace_rejects_ammo_then_reservation_collision(self):
        self.command()
        before = self.state()
        with self.assertRaises(TransactionError) as raised:
            self.store.reserve_vehicle(account_id=ACCOUNT, command_id="ammo-1", vehicle_id=IS7,
                                       expected_revision=1, battle_id="battle-a")
        self.assertEqual(raised.exception.code, "DUPLICATE_PAYLOAD_MISMATCH")
        self.assertEqual(self.state(), before)

    def test_incompatible_known_shell_even_explicit_zero_is_rejected(self):
        incompatible = next(shell for shell in SHELLS if shell not in self.ms_shells)
        for quantity in (0, 1):
            with self.subTest(quantity=quantity):
                self.reject_unchanged("INCOMPATIBLE_SHELL", desired={incompatible: quantity})

    def test_unknown_shell_and_wrong_key_type_are_rejected(self):
        self.reject_unchanged("INCOMPATIBLE_SHELL", desired={"not-in-catalog": 1})
        self.reject_unchanged("INCOMPATIBLE_SHELL", desired={1: 1})

    def test_capacity_uses_sum_across_shell_types(self):
        capacity = MOUNTS["ms1-stock"].capacity
        self.reject_unchanged("CAPACITY_EXCEEDED", desired={self.ms_shells[0]: capacity + 1})
        self.reject_unchanged("CAPACITY_EXCEEDED",
                              desired={self.ms_shells[0]: capacity, self.ms_shells[1]: 1})

    def test_insufficient_stock_does_not_partially_unload_existing_ammo(self):
        self.store.create_profile("poor", ("poor-ms1",))
        self.store.seed_test_ammunition("poor", {"poor-ms1": "ms1-stock"}, {self.ms_shells[0]: 10})
        args = {"authenticated_account_id": "poor", "account_id": "poor", "vehicle_id": "poor-ms1"}
        self.command(**args, desired={self.ms_shells[0]: 10})
        self.reject_unchanged("INSUFFICIENT_STOCK", **args, command_id="poor-change",
                              expected_revision=1, desired={self.ms_shells[1]: 1})

    def test_invalid_quantity_types_and_bounds_are_rejected(self):
        for value in (True, False, -1, 1.0, "1", None, MAX_DEPOT + 1, 10**100):
            with self.subTest(value=value):
                self.reject_unchanged("INVALID_QUANTITY", desired={self.ms_shells[0]: value})

    def test_wrong_or_oversize_shell_map_is_rejected(self):
        for value in (None, [], [(self.ms_shells[0], 1)],
                      {f"shell-{index}": 0 for index in range(len(SHELLS) + 1)}):
            with self.subTest(value=value):
                self.reject_unchanged("INVALID_INPUT", desired=value)

    def test_revision_input_is_strict_and_bounded(self):
        for revision in (True, -1, 0.0, "0", 2**31):
            with self.subTest(revision=revision):
                self.reject_unchanged("INVALID_INPUT", expected_revision=revision)

    def test_command_ids_are_bounded_visible_ascii(self):
        for value in ("", "contains space", "\n", "x" * 97, "кириллица", None):
            with self.subTest(value=value):
                self.reject_unchanged("INVALID_INPUT", command_id=value)

    def test_purchase_funding_is_explicitly_unavailable(self):
        for funding in ("credits", "gold", "purchase", None):
            with self.subTest(funding=funding):
                self.reject_unchanged("PURCHASE_UNSUPPORTED", funding=funding)

    def test_failure_at_each_write_boundary_rolls_back_and_survives_reopen(self):
        for failpoint in ("after_depot_update", "after_ammo_update", "after_snapshot_update", "before_commit"):
            with self.subTest(failpoint=failpoint):
                before = self.state()
                self.store.failpoint = failpoint
                self.reject_unchanged("INJECTED_FAILURE")
                self.reopen()
                self.assertEqual(self.state(), before)
        self.command()
        self.assertEqual(self.profile()["revision"], 1)
        self.assertEqual(self.store.ledger_count(ACCOUNT), 1)

    def test_repeated_bootstrap_cannot_issue_stock_twice(self):
        before = self.state()
        with self.assertRaises(TransactionError) as raised:
            self.store.seed_test_ammunition(ACCOUNT, self.mounts, self.depot)
        self.assertEqual(raised.exception.code, "ALREADY_SEEDED_OR_USED")
        self.assertEqual(self.state(), before)

    def test_zero_stock_bootstrap_still_cannot_be_repeated(self):
        self.store.create_profile("zero", ("zero-ms1",))
        self.store.seed_test_ammunition("zero", {"zero-ms1": "ms1-stock"}, {})
        before = self.state()
        with self.assertRaises(TransactionError) as raised:
            self.store.seed_test_ammunition("zero", {"zero-ms1": "ms1-stock"}, self.depot)
        self.assertEqual(raised.exception.code, "ALREADY_SEEDED_OR_USED")
        self.assertEqual(self.state(), before)

    def test_bootstrap_requires_all_and_only_owned_vehicles(self):
        self.store.create_profile("new", ("new-ms1", "new-is7"))
        for mounts in ({"new-ms1": "ms1-stock"}, {"other": "ms1-stock"}):
            with self.subTest(mounts=mounts):
                before = self.state()
                with self.assertRaises(TransactionError) as raised:
                    self.store.seed_test_ammunition("new", mounts, self.depot)
                self.assertEqual(raised.exception.code, "UNKNOWN_VEHICLE")
                self.assertEqual(self.state(), before)

    def test_bootstrap_refuses_unknown_mount_or_previously_used_profile(self):
        self.store.create_profile("new", ("new-ms1",))
        before = self.state()
        with self.assertRaises(TransactionError) as raised:
            self.store.seed_test_ammunition("new", {"new-ms1": "unverified-gun"}, self.depot)
        self.assertEqual(raised.exception.code, "UNSUPPORTED_MOUNT")
        self.assertEqual(self.state(), before)
        self.store.reserve_vehicle(account_id="new", command_id="new-reserve", vehicle_id="new-ms1",
                                   expected_revision=0, battle_id="battle-b")
        before = self.state()
        with self.assertRaises(TransactionError) as raised:
            self.store.seed_test_ammunition("new", {"new-ms1": "ms1-stock"}, self.depot)
        self.assertEqual(raised.exception.code, "ALREADY_SEEDED_OR_USED")
        self.assertEqual(self.state(), before)

    def test_bootstrap_failure_rolls_back_all_rows_and_allows_clean_retry(self):
        self.store.create_profile("new", ("new-ms1",))
        before = self.state()
        self.store.failpoint = "before_seed_commit"
        with self.assertRaises(TransactionError) as raised:
            self.store.seed_test_ammunition("new", {"new-ms1": "ms1-stock"}, self.depot)
        self.assertEqual(raised.exception.code, "INJECTED_FAILURE")
        self.reopen()
        self.assertEqual(self.state(), before)
        self.store.seed_test_ammunition("new", {"new-ms1": "ms1-stock"}, self.depot)
        self.assertEqual(self.profile("new")["depot"], self.depot)

    def test_unseeded_vehicle_service_is_explicitly_unsupported(self):
        self.store.create_profile("new", ("new-ms1",))
        self.reject_unchanged("UNSUPPORTED_MOUNT", authenticated_account_id="new", account_id="new",
                              vehicle_id="new-ms1")

    def test_unbounded_vehicle_iterable_is_stopped_at_owned_limit(self):
        seen = []
        def vehicles():
            index = 0
            while True:
                seen.append(index)
                yield f"vehicle-{index}"
                index += 1
        before = self.state()
        with self.assertRaises(TransactionError) as raised:
            self.store.create_profile("too-many", vehicles())
        self.assertEqual(raised.exception.code, "INVALID_INPUT")
        self.assertEqual(len(seen), MAX_OWNED + 1)
        self.assertEqual(self.state(), before)

    def test_legacy_p09b_database_is_not_silently_migrated(self):
        legacy_path = Path(self.tempdir.name) / "legacy.sqlite3"
        with GameProfileStore(legacy_path) as legacy:
            legacy.initialize()
            legacy.create_profile("legacy", ("legacy-ms1",))
        before = legacy_path.read_bytes()
        with AmmoServiceStore(legacy_path) as candidate:
            with self.assertRaises(TransactionError) as raised:
                candidate.initialize()
            self.assertEqual(raised.exception.code, "UNSUPPORTED_STORE_SCHEMA")
        self.assertEqual(legacy_path.read_bytes(), before)

    def test_unknown_extension_schema_is_rejected_on_reopen(self):
        self.write("UPDATE p09c_schema SET version = ?", ("p09c-future.v99",))
        before = self.state()
        with AmmoServiceStore(self.db) as candidate:
            with self.assertRaises(TransactionError) as raised:
                candidate.initialize()
            self.assertEqual(raised.exception.code, "UNSUPPORTED_STORE_SCHEMA")
        self.assertEqual(self.state(), before)

    def test_corrupt_snapshot_digest_rejects_new_command_and_replay(self):
        self.command()
        self.write("UPDATE game_snapshot SET snapshot_sha256 = ? WHERE account_id = ?", ("0" * 64, ACCOUNT))
        self.reject_unchanged("CORRUPT_STORE")
        self.reject_unchanged("CORRUPT_STORE", command_id="new", expected_revision=1)

    def test_snapshot_catalog_binding_is_verified_even_with_valid_digest(self):
        value = self.profile()
        value["catalog_sha256"] = "0" * 64
        raw = json.dumps(value, sort_keys=True, separators=(",", ":"))
        self.write("UPDATE game_snapshot SET snapshot_json = ?, snapshot_sha256 = ? WHERE account_id = ?",
                   (raw, hashlib.sha256(raw.encode("ascii")).hexdigest(), ACCOUNT))
        self.reject_unchanged("CORRUPT_STORE")

    def test_depot_and_loaded_row_projection_corruption_fails_closed(self):
        self.write("UPDATE p09c_ammo_depot SET quantity = quantity - 1 WHERE account_id = ? AND shell_id = ?",
                   (ACCOUNT, self.ms_shells[0]))
        self.reject_unchanged("CORRUPT_STORE")
        self.write("UPDATE p09c_ammo_depot SET quantity = quantity + 1 WHERE account_id = ? AND shell_id = ?",
                   (ACCOUNT, self.ms_shells[0]))
        self.profile()  # Prove the first corruption was restored before the next.
        loaded = self.loaded()
        loaded[self.ms_shells[0]] = 1
        self.write("UPDATE p09c_ammo_mount SET loaded_json = ? WHERE account_id = ? AND vehicle_id = ?",
                   (json.dumps(loaded), ACCOUNT, MS1))
        self.reject_unchanged("CORRUPT_STORE")

    def test_corrupt_loaded_json_is_bounded_and_rejected(self):
        original = self.store.connection.execute(
            "SELECT loaded_json FROM p09c_ammo_mount WHERE account_id = ? AND vehicle_id = ?", (ACCOUNT, MS1)
        ).fetchone()[0]
        shell_json = json.dumps(self.ms_shells[0])
        malformed = ("{" + shell_json + ":0," + shell_json + ":1}",
                     "{" + shell_json + ":NaN}",
                     '{"nested":' + "[" * 20 + "0" + "]" * 20 + "}",
                     " " * (16 * 1024 + 1), "[]")
        for raw in malformed:
            with self.subTest(raw=raw[:80]):
                self.write("UPDATE p09c_ammo_mount SET loaded_json = ? WHERE account_id = ? AND vehicle_id = ?",
                           (raw, ACCOUNT, MS1))
                self.reject_unchanged("CORRUPT_STORE")
                self.write("UPDATE p09c_ammo_mount SET loaded_json = ? WHERE account_id = ? AND vehicle_id = ?",
                           (original, ACCOUNT, MS1))
                self.profile()

    def test_corrupt_ledger_result_binding_and_types_reject_replay(self):
        self.command()
        original = self.store.connection.execute(
            "SELECT result_json FROM game_command_ledger WHERE account_id = ? AND command_id = ?", (ACCOUNT, "ammo-1")
        ).fetchone()[0]
        original_digest = hashlib.sha256(original.encode("ascii")).hexdigest()
        mutations = ({"account_id": "foreign"}, {"catalog_sha256": "0" * 64},
                     {"source_revision": False}, {"destination_revision": 7},
                     {"financial_status": "PAID"}, {"replayed": True},
                     {"command_id": "other"}, {"loaded": {self.ms_shells[0]: True}},
                     {"depot_delta": {self.ms_shells[0]: True}})
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                value = json.loads(original)
                value.update(mutation)
                raw = json.dumps(value, sort_keys=True, separators=(",", ":"))
                # Preserve checksum validity to exercise semantic bindings,
                # independently from the checksum-corruption test below.
                self.write("UPDATE game_command_ledger SET result_json = ?, p09c_result_sha256 = ? "
                           "WHERE account_id = ? AND command_id = ?",
                           (raw, hashlib.sha256(raw.encode("ascii")).hexdigest(), ACCOUNT, "ammo-1"))
                self.reject_unchanged("CORRUPT_STORE")
                self.write("UPDATE game_command_ledger SET result_json = ?, p09c_result_sha256 = ? "
                           "WHERE account_id = ? AND command_id = ?",
                           (original, original_digest, ACCOUNT, "ammo-1"))
                self.assertTrue(self.command()["replayed"])

    def test_ledger_checksum_rejects_in_bounds_depot_delta_sign_corruption(self):
        result = self.command()
        self.assertEqual(result["depot_delta"][self.ms_shells[0]], -20)
        result["depot_delta"][self.ms_shells[0]] = 20
        self.write("UPDATE game_command_ledger SET result_json = ? WHERE account_id = ? AND command_id = ?",
                   (json.dumps(result), ACCOUNT, "ammo-1"))
        self.reject_unchanged("CORRUPT_STORE")

    def test_corrupt_depot_rejects_inherited_reservation_replay(self):
        args = {"account_id": ACCOUNT, "command_id": "reserve", "vehicle_id": MS1,
                "expected_revision": 0, "battle_id": "battle-a"}
        first = self.store.reserve_vehicle(**args)
        self.assertEqual(self.store.reserve_vehicle(**args), {**first, "replayed": True})
        self.write("UPDATE p09c_ammo_depot SET quantity = quantity - 1 WHERE account_id = ? AND shell_id = ?",
                   (ACCOUNT, self.ms_shells[0]))
        before = self.state()
        with self.assertRaises(TransactionError) as raised:
            self.store.reserve_vehicle(**args)
        self.assertEqual(raised.exception.code, "CORRUPT_STORE")
        self.assertEqual(self.state(), before)
        self.assertFalse(self.store.connection.in_transaction)

    def test_revision_exhaustion_rolls_back_ammo_and_inherited_reservation(self):
        self.store._save_snapshot(ACCOUNT, 2**31 - 1)
        self.store.connection.commit()
        self.reject_unchanged("REVISION_EXHAUSTED", expected_revision=2**31 - 1)
        before = self.state()
        with self.assertRaises(TransactionError):
            self.store.reserve_vehicle(account_id=ACCOUNT, command_id="too-far", vehicle_id=MS1,
                                       expected_revision=2**31 - 1, battle_id="battle-a")
        self.assertEqual(self.state(), before)
        self.assertFalse(self.store.connection.in_transaction)

    def test_depot_overflow_on_unload_is_atomic(self):
        self.command()
        # Simulate a consistent already-owned inventory near the policy bound;
        # this is a fixture edit, not an accepted grant or economy operation.
        self.write("UPDATE p09c_ammo_depot SET quantity = ? WHERE account_id = ? AND shell_id = ?",
                   (MAX_DEPOT, ACCOUNT, self.ms_shells[0]))
        self.store._save_snapshot(ACCOUNT, 1)
        self.store.connection.commit()
        self.reject_unchanged("DEPOT_OVERFLOW", command_id="overflow", expected_revision=1, desired={})

    def run_race(self, commands):
        barrier = threading.Barrier(2)
        def invoke(command):
            # Each connection is constructed in its own actual worker thread.
            with AmmoServiceStore(self.db) as store:
                store.initialize()
                barrier.wait(timeout=10)
                try:
                    return ("ok", store.set_ammunition(**command))
                except TransactionError as error:
                    return ("error", error.code)
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(invoke, command) for command in commands]
            return [future.result(timeout=15) for future in futures]

    def race_command(self, **overrides):
        command = {"authenticated_account_id": ACCOUNT, "account_id": ACCOUNT,
                   "command_id": "race", "vehicle_id": MS1, "expected_revision": 0,
                   "desired": {self.ms_shells[0]: 20}}
        command.update(overrides)
        return command

    def test_concurrent_same_command_commits_once_and_replays_once(self):
        original = self.conservation()
        results = self.run_race([self.race_command(), self.race_command()])
        self.assertEqual([kind for kind, _ in results], ["ok", "ok"])
        replies = [result for _, result in results]
        self.assertEqual(sorted(result["replayed"] for result in replies), [False, True])
        self.assertEqual({**replies[0], "replayed": False}, {**replies[1], "replayed": False})
        self.assertEqual(self.profile()["revision"], 1)
        self.assertEqual(self.store.ledger_count(ACCOUNT), 1)
        self.assertEqual(self.loaded()[self.ms_shells[0]], 20)
        self.assertEqual(self.profile()["depot"][self.ms_shells[0]], 280)
        self.assertEqual(self.conservation(), original)
        before = self.state()
        self.reopen()
        self.assertEqual(self.state(), before)

    def test_concurrent_distinct_commands_with_same_revision_have_one_stale_loser(self):
        original = self.conservation()
        results = self.run_race([
            self.race_command(command_id="race-ms1"),
            self.race_command(command_id="race-is7", vehicle_id=IS7, desired={self.is_shells[0]: 5}),
        ])
        self.assertEqual(sorted(kind for kind, _ in results), ["error", "ok"])
        self.assertEqual(next(value for kind, value in results if kind == "error"), "STALE_REVISION")
        winner = next(value for kind, value in results if kind == "ok")
        other = IS7 if winner["vehicle_id"] == MS1 else MS1
        self.assertEqual(sum(self.loaded(other).values()), 0)
        self.assertEqual(self.loaded(winner["vehicle_id"]), winner["loaded"])
        self.assertEqual(self.profile()["revision"], 1)
        self.assertEqual(self.store.ledger_count(ACCOUNT), 1)
        self.assertEqual(self.conservation(), original)

    def test_concurrent_same_key_with_different_payload_has_one_mismatch_loser(self):
        original = self.conservation()
        results = self.run_race([
            self.race_command(desired={self.ms_shells[0]: 10}),
            self.race_command(desired={self.ms_shells[0]: 20}),
        ])
        self.assertEqual(sorted(kind for kind, _ in results), ["error", "ok"])
        self.assertEqual(next(value for kind, value in results if kind == "error"), "DUPLICATE_PAYLOAD_MISMATCH")
        winner = next(value for kind, value in results if kind == "ok")
        self.assertEqual(self.loaded(), winner["loaded"])
        self.assertEqual(self.profile()["revision"], 1)
        self.assertEqual(self.store.ledger_count(ACCOUNT), 1)
        self.assertEqual(self.conservation(), original)


if __name__ == "__main__":
    unittest.main()
