from contextlib import closing
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]
import int_user_settings as settings
from server.domain import service as domain

ACCOUNT, OTHER = "00000000-0000-0000-0000-000000000001", "00000000-0000-0000-0000-000000000002"


def body(account=ACCOUNT, pairs=(), keys=(), native=7):
    return json.dumps({"account_id": account, "native_database_id": native, "set": list(pairs), "delete": list(keys)}).encode()


class Store(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.database = Path(self.directory.name) / "game.sqlite"

    def execute(self, *args, **kwargs):
        return settings.execute(self.database, ACCOUNT, body(*args, **kwargs))["settings"]

    def test_write_read_update_delete_are_scoped_to_one_account(self):
        self.assertEqual(self.execute(pairs=[[1, 5], [43, -1], [0, 11]]), [[0, 11], [1, 5], [43, -1]])
        self.assertEqual(self.execute(pairs=[[1, 6]], keys=[43]), [[0, 11], [1, 6]])
        self.assertEqual(self.execute(), [[0, 11], [1, 6]])
        self.assertEqual(settings.execute(self.database, OTHER, body(OTHER))["settings"], [])

    def test_the_first_login_batch_with_marks_on_gun_is_stored(self):
        pairs = [[key, 1] for key in range(51)] + [[500, 0]]
        stored = self.execute(pairs=pairs)
        self.assertEqual(len(stored), 52)
        self.assertIn([500, 0], stored)
        for key in (499, 501):
            with self.assertRaises(ValueError):
                self.execute(pairs=[[key, 1]])

    def test_a_change_is_all_or_nothing(self):
        self.execute(pairs=[[2, 1]])
        with self.assertRaises(sqlite3.IntegrityError):
            with closing(sqlite3.connect(self.database)) as db:
                db.execute("CREATE TRIGGER refuse BEFORE INSERT ON project_int_user_setting WHEN NEW.key=9 BEGIN SELECT RAISE(ABORT,'x'); END")
            self.execute(pairs=[[3, 1], [9, 1]])
        with closing(sqlite3.connect(self.database)) as db:
            db.execute("DROP TRIGGER refuse")
        self.assertEqual(self.execute(), [[2, 1]])

    def test_closed_request_shape(self):
        for pairs, keys in (([[57, 1]], []), ([[-1, 1]], []), ([[1, 2**31]], []), ([[1, -2**31 - 1]], []), ([[True, 1]], []),
                            ([[1, 1.5]], []), ([[1]], []), ([[1, 2, 3]], []), ([[1, 1], [1, 2]], []), ([[1, 1]], [1]),
                            ([], [0]), ([], [57]), ([], [1, 1]), ([[k % 57, 0] for k in range(65)], [])):
            with self.subTest(pairs=pairs, keys=keys), self.assertRaises(ValueError):
                self.execute(pairs=pairs, keys=keys)
        for raw in (b"[]", json.dumps({"account_id": ACCOUNT, "set": [], "delete": []}).encode(), body(OTHER)):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                settings.execute(self.database, ACCOUNT, raw)
        self.assertFalse(self.database.exists())


class Handler(unittest.TestCase):
    def domain(self, database, accounts):
        instance = domain.Domain.__new__(domain.Domain)
        instance.contexts = {account: object() for account in accounts}
        instance.native_ids = dict(accounts)
        instance.config = type("Config", (), {"database": database, "accounts": {a: {"late": False} for a in accounts}})()
        instance.rate = type("Rate", (), {"take": lambda self: True})()
        instance.lanes = {account: domain.AccountLane() for account in accounts}
        import threading
        instance.slots = threading.BoundedSemaphore(2)
        instance.watchdog = domain.Watchdog()
        return instance

    def header(self, account=ACCOUNT, op="int-settings", key=None):
        return {"schema": domain.SCHEMA, "id": 1, "op": op, "account_id": account, "key": key}

    def test_operation_is_authorized_by_account_and_native_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "game.sqlite"
            instance = self.domain(database, {ACCOUNT: 7})
            status, error, reply = instance.handle(self.header(), body(pairs=[[43, 5]]))
            self.assertEqual((status, error), (200, None))
            self.assertEqual(json.loads(reply), {"account_id": ACCOUNT, "settings": [[43, 5]]})
            self.assertEqual(instance.handle(self.header(OTHER), body(OTHER))[0], 403)
            self.assertEqual(instance.handle(self.header(), body(OTHER))[0], 403)
            self.assertEqual(instance.handle(self.header(), body(native=8))[0], 403)
            self.assertEqual(instance.handle(self.header(key="k"), body())[0], 400)
            self.assertEqual(instance.handle(self.header(), body(pairs=[[57, 1]]))[0], 400)
            self.assertEqual(instance.handle(self.header(), b"\xff")[0], 400)
            self.assertEqual(json.loads(instance.handle(self.header(), body())[2])["settings"], [[43, 5]])


if __name__ == "__main__":
    unittest.main()
