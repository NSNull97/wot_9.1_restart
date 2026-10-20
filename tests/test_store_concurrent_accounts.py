"""Concurrent writers of different accounts on one game SQLite file.

The bridge runs one Python worker process per account request; different
accounts may now overlap. These tests use real separate processes on the same
database file, the shared GameProfileStore transaction (``BEGIN IMMEDIATE``,
busy timeout 2 s), and both WAL (what the bridge sets on game.sqlite) and the
default rollback journal.
"""
from __future__ import annotations

from contextlib import closing
from pathlib import Path
import json
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from game_profile_tx import GameProfileStore

WORKER = r"""
import json, sys, time
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from game_profile_tx import GameProfileStore, TransactionError
db, start, account, command, vehicle = sys.argv[2:7]
while not Path(start).exists():
    time.sleep(0.005)
store = GameProfileStore(db)
try:
    result = store.reserve_vehicle(account_id=account, command_id=command, vehicle_id=vehicle,
                                   expected_revision=0, battle_id="battle-" + account)
    print(json.dumps({"status": result["status"], "revision": result["destination_revision"]}))
except TransactionError as error:
    print(json.dumps({"status": "error", "code": error.args[0]}))
except Exception as error:  # sqlite3.OperationalError: explicit failure, no partial write
    print(json.dumps({"status": "error", "code": type(error).__name__, "message": str(error)}))
finally:
    store.close()
"""


class ConcurrentAccountWriterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory(prefix="store-concurrency-")
        self.root = Path(self.tempdir.name)
        self.db = self.root / "game.sqlite"

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def prepare(self, wal: bool, accounts: list[str]) -> None:
        store = GameProfileStore(self.db)
        try:
            if wal:
                self.assertEqual(store.connection.execute("PRAGMA journal_mode=WAL").fetchone()[0], "wal")
            store.initialize()
            for account in accounts:
                store.create_profile(account, ("ms1", "t34"))
        finally:
            store.close()

    def race(self, jobs: list[tuple[str, str, str]]) -> list[dict]:
        start = self.root / "start"
        processes = [subprocess.Popen([sys.executable, "-B", "-c", WORKER, str(ROOT / "tools"), str(self.db), str(start), *job],
                                      stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for job in jobs]
        time.sleep(0.5)  # every worker has imported and is polling the barrier
        start.write_text("go", encoding="ascii")
        results = []
        for process in processes:
            out, err = process.communicate(timeout=60)
            self.assertEqual(process.returncode, 0, err)
            results.append(json.loads(out))
        return results

    def revisions(self) -> dict[str, int]:
        with closing(sqlite3.connect(self.db)) as connection:
            return dict(connection.execute("SELECT account_id, revision FROM game_snapshot ORDER BY account_id").fetchall())

    def ledger(self) -> dict[str, int]:
        with closing(sqlite3.connect(self.db)) as connection:
            return dict(connection.execute("SELECT account_id, COUNT(*) FROM game_command_ledger GROUP BY account_id").fetchall())

    def assert_independent_accounts_all_commit(self, wal: bool) -> None:
        accounts = [f"acct-{n}" for n in range(4)]
        self.prepare(wal, accounts)
        results = self.race([(account, "cmd-" + account, "t34") for account in accounts])
        self.assertEqual(results, [{"status": "reserved", "revision": 1}] * 4)
        self.assertEqual(self.revisions(), {account: 1 for account in accounts})
        self.assertEqual(self.ledger(), {account: 1 for account in accounts})
        with closing(sqlite3.connect(self.db)) as connection:
            self.assertEqual(connection.execute("PRAGMA integrity_check").fetchone()[0], "ok")

    def test_four_accounts_commit_concurrently_in_wal_mode(self):
        self.assert_independent_accounts_all_commit(wal=True)

    def test_four_accounts_commit_concurrently_with_rollback_journal(self):
        self.assert_independent_accounts_all_commit(wal=False)

    def test_same_account_race_commits_exactly_one_revision(self):
        self.prepare(True, ["acct-a"])
        results = self.race([("acct-a", "cmd-1", "ms1"), ("acct-a", "cmd-2", "t34")])
        self.assertEqual(sorted(r["status"] for r in results), ["error", "reserved"])
        self.assertEqual([r["code"] for r in results if r["status"] == "error"], ["STALE_REVISION"])
        self.assertEqual(self.revisions(), {"acct-a": 1})
        self.assertEqual(self.ledger(), {"acct-a": 1})

    def test_writer_held_past_busy_timeout_fails_other_account_explicitly_without_change(self):
        self.prepare(True, ["acct-a", "acct-b"])
        holder = sqlite3.connect(self.db, isolation_level=None)
        try:
            holder.execute("BEGIN IMMEDIATE")
            started = time.monotonic()
            result = self.race([("acct-b", "cmd-b", "t34")])[0]
            elapsed = time.monotonic() - started
        finally:
            holder.execute("ROLLBACK"); holder.close()
        self.assertEqual((result["status"], result["code"]), ("error", "OperationalError"))
        self.assertIn("locked", result["message"])
        self.assertGreaterEqual(elapsed, 2.0)
        self.assertEqual(self.revisions(), {"acct-a": 0, "acct-b": 0})
        self.assertEqual(self.ledger(), {})


if __name__ == "__main__":
    unittest.main()
