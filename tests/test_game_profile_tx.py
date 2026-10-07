"""Meaningful bounded tests for the isolated P09B persistence harness."""
from __future__ import annotations

from pathlib import Path
import hashlib
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from game_profile_tx import GameProfileStore, TransactionError, _run_self_check


class GameProfileTransactionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory(prefix="p09b-test-")
        self.db = Path(self.tempdir.name) / "profile.sqlite3"
        self.store = GameProfileStore(self.db)
        self.store.initialize()
        self.store.create_profile("acct-a", ("ms1", "is7"))

    def tearDown(self) -> None:
        self.store.close()
        self.tempdir.cleanup()

    def reserve(self, **overrides: object) -> dict:
        values = {
            "account_id": "acct-a", "command_id": "cmd-1", "vehicle_id": "is7",
            "expected_revision": 0, "battle_id": "battle-a",
        }
        values.update(overrides)
        return self.store.reserve_vehicle(**values)  # type: ignore[arg-type]

    def test_success_atomically_advances_snapshot_and_ledger(self):
        result = self.reserve()
        self.assertEqual(result["status"], "reserved")
        self.assertEqual(result["source_revision"], 0)
        self.assertEqual(result["destination_revision"], 1)
        self.assertEqual(self.store.read_profile("acct-a")["revision"], 1)
        self.assertEqual(self.store.ledger_count("acct-a"), 1)
        vehicles = {item["vehicle_id"]: item for item in self.store.read_profile("acct-a")["vehicles"]}
        self.assertEqual(vehicles["is7"]["state"], "reserved")
        self.assertEqual(vehicles["is7"]["battle_id"], "battle-a")

    def test_exact_duplicate_replays_without_second_revision(self):
        first = self.reserve()
        replay = self.reserve()
        self.assertFalse(first["replayed"])
        self.assertTrue(replay["replayed"])
        self.assertEqual({**first, "replayed": True}, replay)
        self.assertEqual(self.store.read_profile("acct-a")["revision"], 1)
        self.assertEqual(self.store.ledger_count("acct-a"), 1)

    def test_duplicate_payload_mismatch_fails_closed(self):
        self.reserve()
        with self.assertRaisesRegex(TransactionError, "DUPLICATE_PAYLOAD_MISMATCH"):
            self.reserve(battle_id="battle-other")
        self.assertEqual(self.store.read_profile("acct-a")["revision"], 1)
        self.assertEqual(self.store.ledger_count("acct-a"), 1)

    def test_stale_revision_fails_before_mutation(self):
        self.reserve()
        with self.assertRaisesRegex(TransactionError, "STALE_REVISION"):
            self.reserve(command_id="cmd-stale", vehicle_id="ms1")
        profile = self.store.read_profile("acct-a")
        self.assertEqual(profile["revision"], 1)
        self.assertEqual(self.store.ledger_count("acct-a"), 1)
        self.assertEqual(next(v for v in profile["vehicles"] if v["vehicle_id"] == "ms1")["state"], "available")

    def test_unknown_and_reserved_vehicle_fail_closed(self):
        with self.assertRaisesRegex(TransactionError, "UNKNOWN_VEHICLE"):
            self.reserve(vehicle_id="does-not-exist")
        self.reserve()
        with self.assertRaisesRegex(TransactionError, "VEHICLE_RESERVED"):
            self.reserve(command_id="cmd-reserved", expected_revision=1)
        self.assertEqual(self.store.ledger_count("acct-a"), 1)

    def test_unknown_account_fails_closed(self):
        with self.assertRaisesRegex(TransactionError, "UNKNOWN_ACCOUNT"):
            self.store.reserve_vehicle(account_id="missing", command_id="cmd", vehicle_id="is7", expected_revision=0, battle_id="b")

    def test_invalid_boolean_revision_is_rejected(self):
        with self.assertRaisesRegex(TransactionError, "INVALID_INPUT"):
            self.reserve(expected_revision=True)

    def test_injected_failure_rolls_back_vehicle_snapshot_and_ledger(self):
        self.store.close()
        self.store = GameProfileStore(self.db, failpoint="after_vehicle_update")
        self.store.initialize()
        with self.assertRaisesRegex(TransactionError, "INJECTED_FAILURE"):
            self.reserve(vehicle_id="is7")
        profile = self.store.read_profile("acct-a")
        self.assertEqual(profile["revision"], 0)
        self.assertEqual(self.store.ledger_count("acct-a"), 0)
        vehicle = next(v for v in profile["vehicles"] if v["vehicle_id"] == "is7")
        self.assertEqual(vehicle["state"], "available")

    def test_reopen_replays_committed_command_and_keeps_rollback_absent(self):
        self.reserve()
        self.store.close()
        self.store = GameProfileStore(self.db)
        self.store.initialize()
        replay = self.reserve()
        self.assertTrue(replay["replayed"])
        self.assertEqual(self.store.read_profile("acct-a")["revision"], 1)
        self.assertEqual(self.store.ledger_count("acct-a"), 1)

    def test_corrupt_nonfinite_snapshot_is_rejected(self):
        raw = '{"account_id":"acct-a","revision":0,"vehicles":[]}'
        # Keep the digest valid so the bounded JSON parser, rather than the
        # integrity check, is the failing boundary.
        self.store.connection.execute(
            "UPDATE game_snapshot SET snapshot_json = ?, snapshot_sha256 = ? WHERE account_id = ?",
            (raw, hashlib.sha256(raw.encode("ascii")).hexdigest(), "acct-a"),
        )
        self.store.connection.commit()
        self.store.connection.execute(
            "UPDATE game_snapshot SET snapshot_json = ?, snapshot_sha256 = ? WHERE account_id = ?",
            ('{"account_id":"acct-a","revision":NaN,"vehicles":[]}', hashlib.sha256(b'{"account_id":"acct-a","revision":NaN,"vehicles":[]}').hexdigest(), "acct-a"),
        )
        self.store.connection.commit()
        with self.assertRaisesRegex(TransactionError, "CORRUPT_STORE"):
            self.store.read_profile("acct-a")

    def test_corrupt_snapshot_digest_is_rejected_before_reservation(self):
        self.store.connection.execute(
            "UPDATE game_snapshot SET snapshot_sha256 = ? WHERE account_id = ?",
            ("0" * 64, "acct-a"),
        )
        self.store.connection.commit()
        with self.assertRaisesRegex(TransactionError, "CORRUPT_STORE"):
            self.reserve()
        self.assertEqual(self.store.ledger_count("acct-a"), 0)
        self.assertEqual(self.store.connection.execute(
            "SELECT state FROM game_vehicle WHERE account_id = ? AND vehicle_id = ?", ("acct-a", "is7")
        ).fetchone()[0], "available")

    def test_snapshot_row_projection_mismatch_is_rejected_before_reservation(self):
        raw = '{"account_id":"acct-a","revision":0,"vehicles":[]}'
        self.store.connection.execute(
            "UPDATE game_snapshot SET snapshot_json = ?, snapshot_sha256 = ? WHERE account_id = ?",
            (raw, hashlib.sha256(raw.encode("ascii")).hexdigest(), "acct-a"),
        )
        self.store.connection.commit()
        with self.assertRaisesRegex(TransactionError, "CORRUPT_STORE"):
            self.reserve()
        self.assertEqual(self.store.ledger_count("acct-a"), 0)
        self.assertEqual(self.store.connection.execute(
            "SELECT state FROM game_vehicle WHERE account_id = ? AND vehicle_id = ?", ("acct-a", "is7")
        ).fetchone()[0], "available")

    def test_self_check_receipt_is_pass(self):
        result = _run_self_check(None)
        self.assertEqual(result["status"], "PASS_P09B_SQLITE_TRANSACTION_HARNESS")
        self.assertTrue(all(result["checks"].values()))


if __name__ == "__main__":
    unittest.main()
