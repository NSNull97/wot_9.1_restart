"""CAT-NATIONS stand database migration: dry run, backup, apply, rollback, refusals.

Synthetic database with the real table shapes; the stand copy run is recorded in
docs/plans/CAT_NATIONS_FIX.md (stands themselves are never touched by tests).
"""
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import cat_nations_migrate as m

ACCOUNT = "12345678-1234-4234-8234-123456789000"


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def sha(text):
    return hashlib.sha256(text.encode("ascii")).hexdigest()


def make(path, catalog=m.OLD, state_text=None, state_sha=None):
    c = sqlite3.connect(str(path))
    for table in m.MARKER_TABLES:
        c.execute("CREATE TABLE %s(version TEXT PRIMARY KEY,catalog_sha256 TEXT NOT NULL)" % table)
        c.execute("INSERT INTO %s VALUES ('v1',?)" % table, (catalog,))
    state = state_text or canonical({"catalog_sha256": catalog, "unlocked": ["vehicle:uk:GB48_FV215b_183"]})
    profile = canonical({"research": {"catalog_sha256": catalog}, "revision": 3})
    snapshot = canonical({"research": {"catalog_sha256": catalog}, "note": "catalog_sha256 in text only"})
    c.execute("CREATE TABLE p09e_research(account_id TEXT PRIMARY KEY,state_json TEXT,state_sha256 TEXT)")
    c.execute("INSERT INTO p09e_research VALUES (?,?,?)", (ACCOUNT, state, state_sha or sha(state)))
    c.execute("CREATE TABLE game_profiles(native_id INTEGER PRIMARY KEY,account_id TEXT UNIQUE,profile_json TEXT)")
    c.execute("INSERT INTO game_profiles(account_id,profile_json) VALUES (?,?)", (ACCOUNT, profile))
    c.execute("CREATE TABLE game_snapshot(account_id TEXT PRIMARY KEY,revision INTEGER,snapshot_json TEXT,snapshot_sha256 TEXT)")
    c.execute("INSERT INTO game_snapshot VALUES (?,3,?,?)", (ACCOUNT, snapshot, sha(snapshot)))
    c.execute("CREATE TABLE game_command_ledger(command_id TEXT,result_json TEXT)")
    c.execute("INSERT INTO game_command_ledger VALUES ('c1',?)", (canonical({"catalog_sha256": catalog}),))
    c.commit()
    c.close()


def rows(path):
    c = sqlite3.connect(str(path))
    try:
        return {t: sorted(map(repr, c.execute("SELECT * FROM " + t)))
                for (t,) in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        c.close()


class Migration(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        self.db = self.dir / "game.sqlite"
        self.backups = self.dir / "backups"
        self.backups.mkdir()

    def test_plan_is_read_only_and_lists_every_change(self):
        make(self.db)
        before = self.db.read_bytes()
        plan = m.plan(self.db, m.OLD, m.NEW)
        self.assertEqual(self.db.read_bytes(), before)
        self.assertEqual(plan["changes"], len(m.MARKER_TABLES) + 3)
        self.assertEqual({r["table"] for r in plan["json_rows"]}, {"p09e_research", "game_profiles", "game_snapshot"})

    def test_apply_then_rollback_restores_every_row_and_keeps_history(self):
        make(self.db)
        original = rows(self.db)
        done = m.migrate(self.db, self.backups, m.OLD, m.NEW)
        self.assertEqual(done["status"], "PASS")
        self.assertEqual(rows(Path(done["backup"])), original)
        self.assertEqual(m.verify(self.db, m.NEW)["status"], "PASS")
        c = sqlite3.connect(str(self.db))
        state, digest = c.execute("SELECT state_json,state_sha256 FROM p09e_research").fetchone()
        ledger = c.execute("SELECT result_json FROM game_command_ledger").fetchone()[0]
        c.close()
        self.assertEqual((json.loads(state)["catalog_sha256"], digest), (m.NEW, sha(state)))
        self.assertIn(m.OLD, ledger)  # history is kept
        with self.assertRaises(m.MigrationError):
            m.migrate(self.db, self.backups, m.OLD, m.NEW)
        m.migrate(self.db, self.backups, m.NEW, m.OLD, label="rollback")
        self.assertEqual(rows(self.db), original)
        self.assertEqual(m.verify(self.db, m.OLD)["status"], "PASS")

    def test_refuses_unknown_catalogue_bad_digest_and_non_canonical_json(self):
        make(self.db, catalog="0" * 64)
        with self.assertRaisesRegex(m.MigrationError, "unknown catalogue"):
            m.plan(self.db, m.OLD, m.NEW)
        for name, kwargs, reason in (
                ("digest.sqlite", dict(state_sha="f" * 64), "stored SHA differs"),
                ("pretty.sqlite", dict(state_text=json.dumps({"catalog_sha256": m.OLD}, indent=1)), "not canonical")):
            db = self.dir / name
            make(db, **kwargs)
            before = db.read_bytes()
            with self.assertRaisesRegex(m.MigrationError, reason):
                m.migrate(db, self.backups, m.OLD, m.NEW)
            self.assertEqual(db.read_bytes(), before)

    def test_fixture_cache_of_current_revision_is_moved_aside_and_back(self):
        make(self.db)
        cache = self.dir / "fixtures" / "p08b-v1" / ACCOUNT
        current, older = cache / "p09d-r3", cache / "p09d-r2"
        for path in (current, older):
            path.mkdir(parents=True)
            (path / "manifest.json").write_text(canonical({"catalog_sha256": m.OLD}), encoding="ascii")
        done = m.migrate(self.db, self.backups, m.OLD, m.NEW, self.dir / "fixtures")
        self.assertEqual(len(done["fixtures_moved"]), 1)
        self.assertFalse(current.exists())
        self.assertTrue(older.exists() and (cache / ("p09d-r3" + m.MOVED_SUFFIX)).is_dir())
        m.migrate(self.db, self.backups, m.NEW, m.OLD, self.dir / "fixtures", label="rollback")
        self.assertTrue(current.is_dir())
        self.assertFalse((cache / ("p09d-r3" + m.MOVED_SUFFIX)).exists())

    def test_rejects_missing_tables_and_unknown_catalogue_in_json(self):
        c = sqlite3.connect(str(self.db))
        c.execute("CREATE TABLE unrelated(id INTEGER)")
        c.close()
        with self.assertRaisesRegex(m.MigrationError, "missing required tables"):
            m.verify(self.db, m.OLD)
        self.db.unlink()
        make(self.db)
        c = sqlite3.connect(str(self.db))
        bad = canonical({"research": {"catalog_sha256": "f" * 64}})
        c.execute("UPDATE game_profiles SET profile_json=?", (bad,))
        c.commit()
        c.close()
        before = rows(self.db)
        for action in (lambda: m.plan(self.db, m.OLD, m.NEW),
                       lambda: m.verify(self.db, m.OLD),
                       lambda: m.migrate(self.db, self.backups, m.OLD, m.NEW)):
            with self.assertRaisesRegex(m.MigrationError, "unknown catalogue in research JSON"):
                action()
        self.assertEqual(rows(self.db), before)

    def test_distinct_ammunition_catalogue_is_not_rewritten(self):
        make(self.db)
        ammo_sha = "f" * 64
        c = sqlite3.connect(str(self.db))
        profile = canonical({"research": {"catalog_sha256": m.OLD},
                             "ammunition_service": {"catalog_sha256": ammo_sha}})
        snapshot = canonical({"research": {"catalog_sha256": m.OLD}, "catalog_sha256": ammo_sha})
        c.execute("UPDATE game_profiles SET profile_json=?", (profile,))
        c.execute("UPDATE game_snapshot SET snapshot_json=?,snapshot_sha256=?", (snapshot, sha(snapshot)))
        c.commit()
        c.close()
        m.migrate(self.db, self.backups, m.OLD, m.NEW)
        c = sqlite3.connect(str(self.db))
        profile = json.loads(c.execute("SELECT profile_json FROM game_profiles").fetchone()[0])
        snapshot = json.loads(c.execute("SELECT snapshot_json FROM game_snapshot").fetchone()[0])
        c.close()
        self.assertEqual(profile["ammunition_service"]["catalog_sha256"], ammo_sha)
        self.assertEqual(snapshot["catalog_sha256"], ammo_sha)
        self.assertEqual(profile["research"]["catalog_sha256"], m.NEW)
        self.assertEqual(snapshot["research"]["catalog_sha256"], m.NEW)
        self.assertEqual(m.verify(self.db, m.NEW)["status"], "PASS")

    def test_rejects_empty_required_table(self):
        make(self.db)
        c = sqlite3.connect(str(self.db))
        c.execute("DELETE FROM p09e_research")
        c.commit()
        c.close()
        with self.assertRaisesRegex(m.MigrationError, "empty table"):
            m.verify(self.db, m.OLD)

    def test_failed_second_fixture_move_rolls_back_transaction_and_first_move(self):
        make(self.db)
        original = rows(self.db)
        root = self.dir / "fixtures"
        paths = [root / part / ACCOUNT / "p09d-r3" for part in ("a", "b")]
        for path in paths:
            path.mkdir(parents=True)
            (path / "manifest.json").write_text(m.OLD, encoding="ascii")
        real_rename = Path.rename
        def fail_second(path, target):
            if path == paths[1]:
                raise OSError("injected move failure")
            return real_rename(path, target)
        with mock.patch.object(Path, "rename", fail_second):
            with self.assertRaisesRegex(m.MigrationError, "PENDING receipt"):
                m.migrate(self.db, self.backups, m.OLD, m.NEW, root)
        self.assertEqual(rows(self.db), original)
        self.assertTrue(all(path.is_dir() for path in paths))
        pending = list(self.backups.glob("*.receipt.json"))
        self.assertEqual(len(pending), 1)
        self.assertEqual(json.loads(pending[0].read_text())["status"], "PENDING")

    def test_receipt_finalization_failure_leaves_recoverable_pending_record(self):
        make(self.db)
        root = self.dir / "fixtures"
        cache = root / ACCOUNT / "p09d-r3"
        cache.mkdir(parents=True)
        (cache / "manifest.json").write_text(m.OLD, encoding="ascii")
        with mock.patch.object(m.os, "replace", side_effect=OSError("injected receipt failure")):
            with self.assertRaisesRegex(m.MigrationError, "database committed.*PENDING receipt"):
                m.migrate(self.db, self.backups, m.OLD, m.NEW, root)
        self.assertEqual(m.verify(self.db, m.NEW)["status"], "PASS")
        receipt_path = next(self.backups.glob("*.receipt.json"))
        receipt = json.loads(receipt_path.read_text())
        self.assertEqual(receipt["status"], "PENDING")
        self.assertEqual(receipt["fixture_moves"], [[str(cache), str(cache.with_name(cache.name + m.MOVED_SUFFIX))]])
        self.assertEqual(m.verify(receipt["backup"], m.OLD)["status"], "PASS")
        self.assertFalse(cache.exists())
        self.assertTrue(cache.with_name(cache.name + m.MOVED_SUFFIX).is_dir())

    def test_busy_database_is_refused_and_unchanged(self):
        make(self.db)
        holder = sqlite3.connect(str(self.db), isolation_level=None)
        holder.execute("BEGIN EXCLUSIVE")
        try:
            with self.assertRaises(sqlite3.OperationalError):
                m.migrate(self.db, self.backups, m.OLD, m.NEW)
        finally:
            holder.execute("ROLLBACK")
            holder.close()
        self.assertEqual(m.verify(self.db, m.OLD)["status"], "PASS")


if __name__ == "__main__":
    unittest.main()
