"""Actual #717 sources and real isolated SQLite configuration reservations.

No live inventory, native installation or battle runtime is touched. Fixture
crew ownership/stock are explicit test inputs, not historical initial grants.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest

from tools.crew_configuration_store import ConfigurationStore, SCHEMA
from game_profile_tx import TransactionError
from p09c_ammo_catalog import MOUNTS, SHELLS
from p09c_ammo_service import AmmoServiceStore
from server.domain import crew_equipment as crew


ROOT = Path(__file__).resolve().parents[1]
CONFIG = Path(os.environ.get("WOT091_CONFIG", ROOT / "config/project.local.json"))
TEMP_ROOT = ROOT / "local/evidence/20261013-p04c-configuration-reservation-01/tmp"
ACCOUNT, MS1, IS7 = "acct-a", "inventory-ms1", "inventory-is7"
OPTICS = "optional_device:coatedOptics"
VENT1 = "optional_device:improvedVentilation_class1"
VENT3 = "optional_device:improvedVentilation_class3"
AIM = "optional_device:enhancedAimDrives"
TABLES = (
    ("game_snapshot", "account_id"), ("game_vehicle", "account_id,vehicle_id"),
    ("game_command_ledger", "account_id,command_id"),
    ("p09c_ammo_mount", "account_id,vehicle_id"), ("p09c_ammo_depot", "account_id,shell_id"),
    ("p09c_schema", "version"), ("crew_configuration_schema", "version"),
    ("crew_vehicle_configuration", "account_id,vehicle_id"),
)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


class ConfigurationReservationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not CONFIG.is_file():
            raise unittest.SkipTest("NOT_RUN: set WOT091_CONFIG to the authorized #717 configuration")

    def setUp(self):
        TEMP_ROOT.mkdir(parents=True, exist_ok=True)
        self.tempdir = tempfile.TemporaryDirectory(prefix="reservation-test-", dir=TEMP_ROOT)
        self.addCleanup(self.tempdir.cleanup)
        self.db = Path(self.tempdir.name) / "profile.sqlite3"
        self.store = ConfigurationStore(self.db, config_path=CONFIG)
        self.addCleanup(lambda: self.store.close())
        self.store.initialize()
        self.store.create_profile(ACCOUNT, (MS1, IS7))
        self.mounts = {MS1: "ms1-stock", IS7: "is7-stock"}
        self.ms_shells, self.is_shells = MOUNTS["ms1-stock"].shell_ids, MOUNTS["is7-stock"].shell_ids
        self.store.seed_test_ammunition(ACCOUNT, self.mounts, {shell: 300 for shell in SHELLS})
        self.raws = {MS1: self.configuration(MS1, [VENT1, OPTICS, None]),
                     IS7: self.configuration(IS7, [VENT3, AIM, OPTICS])}

    def configuration(self, vehicle_id, devices):
        assembly = self.store.assemblies[self.mounts[vehicle_id]]
        vehicle = next(v for v in crew.VEHICLES if v.definition_id == assembly.vehicle_definition_id)
        value = {"format": crew.FORMAT, "policy": crew.POLICY,
                 "account_id": ACCOUNT, "vehicle_inventory_id": vehicle_id,
                 "vehicle_definition_id": vehicle.definition_id, "configuration_revision": 1,
                 "component_configuration_sha256": assembly.component_configuration_sha256,
                 "optional_devices": devices,
                 "crew": [{"crew_id": vehicle_id + "-crew-" + str(seat), "seat": seat,
                           "role": roles[0], "role_level": 100,
                           "trained_vehicle_definition_id": vehicle.definition_id,
                           "vehicle_inventory_id": vehicle_id, "healthy": True, "skills": []}
                          for seat, roles in enumerate(vehicle.seats)]}
        return crew.canonical(value)

    def seed(self, raws=None):
        self.store.seed_test_configurations(ACCOUNT, self.raws if raws is None else raws)

    def ready(self):
        self.seed()
        self.ammo()

    def ammo_arguments(self, **changes):
        value = {"authenticated_account_id": ACCOUNT, "account_id": ACCOUNT,
                 "command_id": "ammo-ms1", "vehicle_id": MS1,
                 "expected_revision": self.profile()["revision"],
                 "desired": {self.ms_shells[0]: 20, self.ms_shells[2]: 5}}
        value.update(changes)
        return value

    def ammo(self, **changes):
        return self.store.set_ammunition(**self.ammo_arguments(**changes))

    def reservation_arguments(self, **changes):
        value = {"authenticated_account_id": ACCOUNT, "account_id": ACCOUNT,
                 "command_id": "reserve-ms1", "vehicle_id": MS1,
                 "expected_revision": self.profile()["revision"],
                 "expected_configuration_sha256": digest(self.raws[MS1]), "battle_id": "battle-a"}
        value.update(changes)
        return value

    def reserve(self, **changes):
        return self.store.reserve_configuration(**self.reservation_arguments(**changes))

    def profile(self):
        return self.store.read_profile(ACCOUNT)

    def state(self):
        return {name: [tuple(row) for row in self.store.connection.execute(
            f"SELECT * FROM {name} ORDER BY {order}")]
                for name, order in TABLES}

    def reopen(self):
        self.store.close()
        self.store = ConfigurationStore(self.db, config_path=CONFIG)
        self.store.initialize()

    def reject_unchanged(self, code, operation):
        before = self.state()
        with self.assertRaises(TransactionError) as raised:
            operation()
        self.assertEqual(raised.exception.code, code)
        self.assertEqual(self.state(), before)
        self.assertFalse(self.store.connection.in_transaction)

    def test_atomic_reservation_freezes_real_mass_crew_devices_and_loaded_ammo(self):
        self.ready()
        before = self.profile()
        result = self.reserve()
        self.assertEqual((result["source_revision"], result["destination_revision"]), (1, 2))
        self.assertEqual(result["schema"], SCHEMA)
        self.assertEqual(self.store.ledger_count(ACCOUNT), 2)
        after = self.profile()
        self.assertEqual(after["depot"], before["depot"])
        self.assertEqual(after["ammunition"], before["ammunition"])
        self.assertEqual(next(v for v in after["vehicles"] if v["vehicle_id"] == MS1),
                         {"vehicle_id": MS1, "state": "reserved", "battle_id": "battle-a"})
        frozen = result["frozen"]
        assembly = self.store.assemblies["ms1-stock"]
        expected = crew.build_snapshot(self.raws[MS1], binding=crew.TrustedBinding(
            ACCOUNT, MS1, 1, digest(self.raws[MS1]), assembly.component_configuration_sha256,
            crew.POLICY_SHA256, assembly.mass_budget))
        self.assertEqual(crew.canonical(frozen["crew_equipment"]), expected.canonical_bytes)
        self.assertEqual(frozen["crew_equipment_sha256"], expected.sha256)
        self.assertEqual(result["frozen_sha256"], digest(crew.canonical(frozen)))
        self.assertEqual(frozen["ammunition"]["loaded"],
                         {self.ms_shells[0]: 20, self.ms_shells[1]: 0, self.ms_shells[2]: 5})
        mass = frozen["crew_equipment"]["mass_check"]
        self.assertEqual((mass["base_mass_grams"], mass["total_mass_grams"], mass["max_load_grams"]),
                         (4691000, 4791000, 4890000))
        self.assertEqual(mass["evidence_sha256"], assembly.evidence_sha256)
        self.assertEqual(frozen["crew_equipment"]["static_modifiers"]["crewLevelIncrease"],
                         {"numerator": 5, "denominator": 1})
        self.assertFalse(frozen["crew_equipment"]["runtime_ready"])
        self.assertEqual(frozen["runtime_acceptance"], "NOT_RUN")

    def test_is7_snapshot_retains_two_loader_seats_and_real_mass(self):
        self.seed()
        self.ammo(vehicle_id=IS7, desired={self.is_shells[0]: 10}, command_id="ammo-is7")
        result = self.reserve(vehicle_id=IS7, expected_configuration_sha256=digest(self.raws[IS7]))
        data = result["frozen"]["crew_equipment"]
        self.assertEqual([m["roles"] for m in data["crew"]],
                         [["commander"], ["gunner"], ["driver"], ["loader"], ["loader", "radioman"]])
        self.assertEqual(data["mass_check"]["base_mass_grams"], 68190000)
        self.assertEqual(data["mass_check"]["total_mass_grams"], 68490000)
        self.assertEqual(data["mass_check"]["max_load_grams"], 70950000)
        self.assertEqual([r["slot"] for r in data["operations_in_slot_order"]], [0, 1, 2])

    def test_configuration_revision_one_is_independent_of_aggregate_zero(self):
        self.seed()
        value = self.profile()
        self.assertEqual(value["revision"], 0)
        self.assertEqual({r["configuration_revision"] for r in value["configurations"]}, {1})
        self.ammo()
        self.ammo(command_id="ammo-again", desired={self.ms_shells[0]: 22})
        self.assertEqual(self.profile()["revision"], 2)
        self.assertEqual(self.reserve()["frozen"]["crew_equipment"]["configuration_revision"], 1)

    def test_replay_after_reopen_and_other_vehicle_service_preserves_original_bytes(self):
        self.ready()
        args = self.reservation_arguments()
        result = self.store.reserve_configuration(**args)
        frozen_bytes = crew.canonical(result["frozen"])
        self.ammo(command_id="ammo-is7", vehicle_id=IS7, desired={self.is_shells[0]: 7})
        before = self.state()
        self.reopen()
        replay = self.store.reserve_configuration(**args)
        self.assertEqual(replay, {**result, "replayed": True})
        self.assertEqual(crew.canonical(replay["frozen"]), frozen_bytes)
        self.assertEqual(self.state(), before)
        self.assertEqual(self.profile()["revision"], 3)

    def test_read_reserved_bytes_survive_reopen_and_other_vehicle_revision_without_writes(self):
        self.ready()
        result = self.reserve()
        args = {"authenticated_account_id": ACCOUNT, "account_id": ACCOUNT,
                "command_id": result["command_id"], "battle_id": result["battle_id"],
                "expected_frozen_sha256": result["frozen_sha256"]}
        expected = crew.canonical(result["frozen"])
        first = self.store.read_reserved_configuration(**args)
        self.assertIs(type(first), bytes)
        self.assertEqual(first, expected)
        self.ammo(command_id="ammo-is7", vehicle_id=IS7, desired={self.is_shells[0]: 7})
        self.reopen()
        before = self.state()
        actual = self.store.read_reserved_configuration(**args)
        self.assertIs(type(actual), bytes)
        self.assertEqual(actual, expected)
        self.assertEqual(digest(actual), result["frozen_sha256"])
        self.assertEqual(self.state(), before)
        self.assertFalse(self.store.connection.in_transaction)

    def test_read_reserved_bytes_rejects_foreign_owner_battle_hash_and_nonreservation_keys(self):
        self.ready()
        result = self.reserve()
        args = {"authenticated_account_id": ACCOUNT, "account_id": ACCOUNT,
                "command_id": result["command_id"], "battle_id": result["battle_id"],
                "expected_frozen_sha256": result["frozen_sha256"]}
        cases = (({"authenticated_account_id": "other"}, "FOREIGN_ACCOUNT"),
                 ({"battle_id": "other-battle"}, "RESERVATION_BINDING_MISMATCH"),
                 ({"expected_frozen_sha256": "0" * 64}, "RESERVATION_BINDING_MISMATCH"),
                 ({"expected_frozen_sha256": "bad"}, "INVALID_INPUT"),
                 ({"command_id": "missing"}, "UNKNOWN_RESERVATION"),
                 ({"command_id": "ammo-ms1"}, "UNKNOWN_RESERVATION"))
        for changes, code in cases:
            with self.subTest(changes=changes):
                self.reject_unchanged(code, lambda: self.store.read_reserved_configuration(**{**args, **changes}))

    def test_read_reserved_bytes_rejects_corrupt_ledger_payload_and_frozen_result(self):
        self.ready()
        result = self.reserve()
        args = {"authenticated_account_id": ACCOUNT, "account_id": ACCOUNT,
                "command_id": result["command_id"], "battle_id": result["battle_id"],
                "expected_frozen_sha256": result["frozen_sha256"]}
        payload_sha = self.store.connection.execute(
            "SELECT payload_sha256 FROM game_command_ledger WHERE account_id=? AND command_id=?",
            (ACCOUNT, result["command_id"])).fetchone()[0]
        self.store.connection.execute("UPDATE game_command_ledger SET payload_sha256=? WHERE account_id=? AND command_id=?",
                                      ("0" * 64, ACCOUNT, result["command_id"]))
        self.store.connection.commit()
        self.reject_unchanged("CORRUPT_STORE", lambda: self.store.read_reserved_configuration(**args))
        altered = json.loads(crew.canonical(result))
        altered["frozen"]["ammunition"]["loaded"][self.ms_shells[0]] += 1
        altered["frozen_sha256"] = digest(crew.canonical(altered["frozen"]))
        raw = crew.canonical(altered)
        self.store.connection.execute(
            "UPDATE game_command_ledger SET payload_sha256=?,result_json=?,p09c_result_sha256=? "
            "WHERE account_id=? AND command_id=?",
            (payload_sha, raw.decode(), digest(raw), ACCOUNT, result["command_id"]))
        self.store.connection.commit()
        self.reject_unchanged("CORRUPT_STORE", lambda: self.store.read_reserved_configuration(
            **{**args, "expected_frozen_sha256": altered["frozen_sha256"]}))

    def test_subject_mismatch_rejects_before_existing_replay(self):
        self.ready()
        args = self.reservation_arguments()
        self.store.reserve_configuration(**args)
        self.reject_unchanged("FOREIGN_ACCOUNT", lambda: self.store.reserve_configuration(
            **{**args, "authenticated_account_id": "acct-foreign"}))

    def test_unknown_vehicle_and_account_reject_atomically(self):
        self.ready()
        args = self.reservation_arguments()
        for change, code in (({"vehicle_id": "unowned"}, "UNKNOWN_VEHICLE"),
                             ({"account_id": "other", "authenticated_account_id": "other"}, "UNKNOWN_ACCOUNT")):
            with self.subTest(change=change):
                self.reject_unchanged(code, lambda: self.store.reserve_configuration(**{**args, **change}))

    def test_stale_aggregate_or_configuration_rejects_without_reservation(self):
        self.ready()
        self.reject_unchanged("STALE_REVISION", lambda: self.reserve(expected_revision=0))
        self.reject_unchanged("STALE_CONFIGURATION", lambda: self.reserve(expected_configuration_sha256="0" * 64))

    def test_missing_configuration_and_empty_ammo_are_explicit(self):
        self.reject_unchanged("MISSING_CONFIGURATION", lambda: self.reserve())
        self.seed()
        self.reject_unchanged("NO_LOADED_AMMUNITION", lambda: self.reserve())

    def test_legacy_reservation_entrypoint_is_disabled(self):
        self.ready()
        self.reject_unchanged("FULL_CONFIGURATION_RESERVATION_REQUIRED", lambda: self.store.reserve_vehicle(
            account_id=ACCOUNT, command_id="bypass", vehicle_id=MS1, expected_revision=1, battle_id="battle-a"))

    def test_already_reserved_vehicle_rejects_new_reservation_and_service(self):
        self.ready()
        self.reserve()
        self.reject_unchanged("VEHICLE_RESERVED", lambda: self.reserve(command_id="reserve-again"))
        self.reject_unchanged("VEHICLE_RESERVED", lambda: self.ammo(command_id="service-reserved"))

    def test_reused_command_key_rejects_changed_battle_and_cross_family(self):
        self.ready()
        args = self.reservation_arguments()
        self.store.reserve_configuration(**args)
        self.reject_unchanged("DUPLICATE_PAYLOAD_MISMATCH", lambda: self.store.reserve_configuration(
            **{**args, "battle_id": "battle-other"}))
        self.reject_unchanged("DUPLICATE_PAYLOAD_MISMATCH", lambda: self.ammo(command_id="reserve-ms1"))
        self.reject_unchanged("DUPLICATE_PAYLOAD_MISMATCH", lambda: self.reserve(command_id="ammo-ms1"))

    def test_seed_cannot_repeat_after_zero_revision_or_commands(self):
        self.seed()
        self.reject_unchanged("ALREADY_SEEDED_OR_USED", lambda: self.seed())
        self.ammo()
        self.reject_unchanged("ALREADY_SEEDED_OR_USED", lambda: self.seed())

    def test_seed_requires_all_and_only_owned_vehicles(self):
        for raws in ({MS1: self.raws[MS1]}, {**self.raws, "unowned": self.raws[MS1]}):
            with self.subTest(keys=list(raws)):
                self.reject_unchanged("UNKNOWN_VEHICLE", lambda: self.seed(raws))

    def test_seed_rejects_duplicate_crew_assignments_across_vehicles(self):
        data = json.loads(self.raws[IS7])
        data["crew"][0]["crew_id"] = json.loads(self.raws[MS1])["crew"][0]["crew_id"]
        self.reject_unchanged("DUPLICATE_CREW_ASSIGNMENT", lambda: self.seed(
            {**self.raws, IS7: crew.canonical(data)}))

    def test_seed_rejects_foreign_owner_foreign_component_revision_and_crew(self):
        original = json.loads(self.raws[MS1])
        for mutation in ({"account_id": "other"}, {"component_configuration_sha256": "0" * 64},
                         {"configuration_revision": 2}, {"vehicle_inventory_id": IS7},
                         {"policy": "unverified"}):
            with self.subTest(mutation=mutation):
                value = {**original, **mutation}
                self.reject_unchanged("INVALID_CONFIGURATION", lambda: self.seed(
                    {**self.raws, MS1: crew.canonical(value)}))

    def test_seed_rejects_cross_vehicle_mount_even_when_configuration_self_consistent(self):
        value = json.loads(self.raws[IS7])
        value["vehicle_inventory_id"] = MS1
        for member in value["crew"]:
            member["vehicle_inventory_id"] = MS1
        self.reject_unchanged("CONFIGURATION_MOUNT_MISMATCH", lambda: self.seed(
            {**self.raws, MS1: crew.canonical(value)}))

    def test_ms1_199kg_reserve_rejects_ventilation_plus_aim_drives(self):
        overweight = self.configuration(MS1, [VENT1, AIM, OPTICS])
        self.reject_unchanged("INVALID_CONFIGURATION", lambda: self.seed({**self.raws, MS1: overweight}))

    def test_configuration_seed_failpoint_rolls_back_complete_assignment(self):
        self.store.failpoint = "before_configuration_seed_commit"
        self.reject_unchanged("INJECTED_FAILURE", lambda: self.seed())
        self.reopen()
        self.seed()
        self.assertEqual(len(self.profile()["configurations"]), 2)

    def test_invalid_raw_json_and_bounds_reject_without_partial_seed(self):
        for raw, code in ((b"[]", "CORRUPT_STORE"), (b"{}", "CONFIGURATION_MOUNT_MISMATCH"),
                          (b"x" * (crew.MAX_BYTES + 1), "INVALID_INPUT"),
                          (bytearray(self.raws[MS1]), "INVALID_INPUT")):
            with self.subTest(kind=type(raw), size=len(raw)):
                self.reject_unchanged(code, lambda: self.seed({**self.raws, MS1: raw}))

    def test_corrupt_configuration_hash_blocks_new_reservation_and_replay(self):
        self.ready()
        args = self.reservation_arguments()
        self.store.reserve_configuration(**args)
        self.store.connection.execute("UPDATE crew_vehicle_configuration SET configuration_sha256=? "
                                      "WHERE account_id=? AND vehicle_id=?", ("0" * 64, ACCOUNT, MS1))
        self.store.connection.commit()
        self.reject_unchanged("CORRUPT_STORE", lambda: self.store.reserve_configuration(**args))
        self.reject_unchanged("CORRUPT_STORE", lambda: self.store.reserve_configuration(
            **{**args, "command_id": "new", "expected_revision": 2}))

    def test_semantic_corruption_with_recomputed_configuration_hash_rejects(self):
        self.ready()
        args = self.reservation_arguments()
        data = json.loads(self.raws[MS1])
        data["crew"][0]["role"] = "driver"
        raw = crew.canonical(data)
        self.store.connection.execute("UPDATE crew_vehicle_configuration SET configuration_json=?, configuration_sha256=? "
                                      "WHERE account_id=? AND vehicle_id=?", (raw.decode(), digest(raw), ACCOUNT, MS1))
        self.store.connection.commit()
        self.reject_unchanged("CORRUPT_STORE", lambda: self.store.reserve_configuration(**args))

    def test_corrupt_ledger_digest_or_semantics_never_replays_success(self):
        self.ready()
        args = self.reservation_arguments()
        result = self.store.reserve_configuration(**args)
        for changed, rehash in (({"battle_id": "other"}, False), ({"battle_id": "other"}, True),
                                ({"source_revision": False}, True), ({"frozen_sha256": "0" * 64}, True)):
            with self.subTest(changed=changed, rehash=rehash):
                raw = crew.canonical({**result, **changed})
                self.store.connection.execute("UPDATE game_command_ledger SET result_json=?,p09c_result_sha256=? "
                                              "WHERE account_id=? AND command_id=?",
                                              (raw.decode(), digest(raw) if rehash else digest(crew.canonical(result)),
                                               ACCOUNT, args["command_id"]))
                self.store.connection.commit()
                before = self.state()
                with self.assertRaises(TransactionError):
                    self.store.reserve_configuration(**args)
                self.assertEqual(self.state(), before)
                self.assertFalse(self.store.connection.in_transaction)

    def test_corrupt_snapshot_hash_and_ammo_projection_block_admission(self):
        self.ready()
        args = self.reservation_arguments()
        self.store.connection.execute("UPDATE p09c_ammo_depot SET quantity=quantity-1 WHERE account_id=? AND shell_id=?",
                                      (ACCOUNT, self.ms_shells[0]))
        self.store.connection.commit()
        self.reject_unchanged("CORRUPT_STORE", lambda: self.store.reserve_configuration(**args))

    def test_invalid_ids_revision_and_hash_are_bounded_before_writes(self):
        self.ready()
        args = self.reservation_arguments()
        for key, values in (("expected_revision", (True, -1, 2**31, 1.0)),
                            ("expected_configuration_sha256", (None, "0" * 63, "G" * 64)),
                            ("command_id", ("", "x" * 97, "with space", "slashes/"))):
            for value in values:
                with self.subTest(key=key, value=value):
                    self.reject_unchanged("INVALID_INPUT", lambda: self.store.reserve_configuration(
                        **{**args, key: value}))

    def test_revision_exhaustion_does_not_reserve_or_write_ledger(self):
        self.ready()
        self.store._save_snapshot(ACCOUNT, 2**31 - 1)
        self.store.connection.commit()
        self.reject_unchanged("REVISION_EXHAUSTED", lambda: self.reserve())

    def test_every_reservation_failpoint_rolls_back_all_rows_and_survives_reopen(self):
        self.ready()
        args = self.reservation_arguments()
        original = self.state()
        for point in ("after_configuration_read", "after_vehicle_update", "after_snapshot_update",
                      "after_ledger_insert", "before_commit"):
            with self.subTest(point=point):
                self.store.failpoint = point
                self.reject_unchanged("INJECTED_FAILURE", lambda: self.store.reserve_configuration(**args))
                self.reopen()
                self.assertEqual(self.state(), original)
        result = self.store.reserve_configuration(**args)
        self.assertEqual(result["destination_revision"], 2)

    def test_legacy_p09c_writer_refuses_extended_snapshot_without_writes(self):
        self.ready()
        before = self.state()
        with AmmoServiceStore(self.db) as legacy:
            legacy.initialize()
            with self.assertRaises(TransactionError) as raised:
                legacy.set_ammunition(**self.ammo_arguments(command_id="legacy"))
            self.assertEqual(raised.exception.code, "CORRUPT_STORE")
            self.assertFalse(legacy.connection.in_transaction)
        self.assertEqual(self.state(), before)

    def run_race(self, operations):
        barrier = threading.Barrier(len(operations))
        def invoke(operation):
            with ConfigurationStore(self.db, config_path=CONFIG) as worker:
                worker.initialize()
                barrier.wait(timeout=10)
                method, args = operation
                try:
                    return ("ok", getattr(worker, method)(**args))
                except TransactionError as error:
                    return ("error", error.code)
        with ThreadPoolExecutor(max_workers=len(operations)) as pool:
            futures = [pool.submit(invoke, operation) for operation in operations]
            return [future.result(timeout=15) for future in futures]

    def test_real_connections_same_command_commit_once_and_replay_once(self):
        self.ready()
        before = self.profile()
        args = self.reservation_arguments()
        results = self.run_race([("reserve_configuration", args), ("reserve_configuration", args)])
        self.assertEqual([kind for kind, value in results], ["ok", "ok"])
        replies = [value for kind, value in results]
        self.assertEqual(sorted(reply["replayed"] for reply in replies), [False, True])
        self.assertEqual({**replies[0], "replayed": False}, {**replies[1], "replayed": False})
        self.assertEqual(self.profile()["revision"], 2)
        self.assertEqual(self.store.ledger_count(ACCOUNT), 2)
        self.assertEqual(self.profile()["depot"], before["depot"])
        self.assertEqual(self.profile()["ammunition"], before["ammunition"])

    def test_real_connections_two_battles_have_one_reservation_winner(self):
        self.ready()
        args = self.reservation_arguments()
        results = self.run_race([("reserve_configuration", args), ("reserve_configuration",
            {**args, "command_id": "reserve-two", "battle_id": "battle-two"})])
        self.assertEqual(sorted(kind for kind, _ in results), ["error", "ok"])
        self.assertEqual(next(value for kind, value in results if kind == "error"), "STALE_REVISION")
        winner = next(value for kind, value in results if kind == "ok")
        vehicle = next(v for v in self.profile()["vehicles"] if v["vehicle_id"] == MS1)
        self.assertEqual(vehicle["battle_id"], winner["battle_id"])
        self.assertEqual(self.store.ledger_count(ACCOUNT), 2)

    def test_real_ammo_vs_reservation_race_has_one_revision_winner(self):
        self.ready()
        original = self.profile()
        results = self.run_race([
            ("reserve_configuration", self.reservation_arguments()),
            ("set_ammunition", self.ammo_arguments(command_id="race-ammo", desired={self.ms_shells[0]: 33})),
        ])
        self.assertEqual(sorted(kind for kind, _ in results), ["error", "ok"])
        self.assertEqual(next(value for kind, value in results if kind == "error"), "STALE_REVISION")
        winner = next(value for kind, value in results if kind == "ok")
        current = self.profile()
        self.assertEqual(current["revision"], 2)
        self.assertEqual(self.store.ledger_count(ACCOUNT), 2)
        loaded = next(a["loaded"] for a in current["ammunition"] if a["vehicle_id"] == MS1)
        if winner["status"] == "reserved":
            self.assertEqual(current["ammunition"], original["ammunition"])
            self.assertEqual(winner["frozen"]["ammunition"]["loaded"], loaded)
            self.assertEqual(current["depot"], original["depot"])
        else:
            self.assertEqual(loaded, {self.ms_shells[0]: 33, self.ms_shells[1]: 0, self.ms_shells[2]: 0})
            self.assertEqual(next(v for v in current["vehicles"] if v["vehicle_id"] == MS1)["state"], "available")
        for shell in self.ms_shells:
            old_load = next(a["loaded"] for a in original["ammunition"] if a["vehicle_id"] == MS1)[shell]
            self.assertEqual(current["depot"][shell] + loaded[shell], original["depot"][shell] + old_load)

    def test_configuration_read_holds_sqlite_writer_lock_until_reservation_commit(self):
        self.ready()
        reached, release = threading.Event(), threading.Event()
        args = self.reservation_arguments()
        ammo_args = self.ammo_arguments(command_id="held-lock-ammo", desired={self.ms_shells[0]: 33})
        class HoldingStore(ConfigurationStore):
            def _failpoint(inner, name):
                if name == "after_configuration_read":
                    reached.set()
                    if not release.wait(timeout=10):
                        raise RuntimeError("test lock release timed out")
                super()._failpoint(name)
        def reserve_held():
            with HoldingStore(self.db, config_path=CONFIG) as worker:
                worker.initialize()
                return worker.reserve_configuration(**args)
        def compete():
            with ConfigurationStore(self.db, config_path=CONFIG) as worker:
                worker.initialize()
                worker.connection.execute("PRAGMA busy_timeout=50")
                try:
                    worker.set_ammunition(**ammo_args)
                except sqlite3.OperationalError as error:
                    return str(error), worker.connection.in_transaction
                raise AssertionError("competing writer unexpectedly committed under held reservation lock")
        with ThreadPoolExecutor(max_workers=2) as pool:
            reservation = pool.submit(reserve_held)
            try:
                self.assertTrue(reached.wait(timeout=10))
                message, in_transaction = pool.submit(compete).result(timeout=5)
                self.assertIn("locked", message.lower())
                self.assertFalse(in_transaction)
            finally:
                release.set()
            result = reservation.result(timeout=10)
        self.assertEqual(result["frozen"]["ammunition"]["loaded"][self.ms_shells[0]], 20)
        self.assertEqual(self.profile()["revision"], 2)
        self.reject_unchanged("STALE_REVISION", lambda: self.store.set_ammunition(**ammo_args))


if __name__ == "__main__":
    unittest.main()
