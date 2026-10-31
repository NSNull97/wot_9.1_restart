"""CAT-NATIONS stand database migration: dry run, backup, apply, rollback, refusals.

Synthetic database with the real table shapes; the stand copy run is recorded in
docs/plans/CAT_NATIONS_FIX.md (stands themselves are never touched by tests).
"""
import ast
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import cat_nations_migrate as m
import p08c_late_results as late
from game_profile_tx import GameProfileStore

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
    c.execute(ledger_ddl())
    c.execute("INSERT INTO game_command_ledger VALUES (?,?,?, ?,0,1,?,NULL)",
              (ACCOUNT, "c1", "synthetic-unrelated", "sha", canonical({"catalog_sha256": catalog})))
    add_empty_reservations(c)
    c.commit()
    c.close()


def rows(path):
    c = sqlite3.connect(str(path))
    try:
        return {t: sorted(map(repr, c.execute("SELECT * FROM " + t)))
                for (t,) in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        c.close()


def late_adapter(connection, catalog):
    value = object.__new__(late.LateResults)
    value.connection = connection
    value.store = SimpleNamespace(catalog=SimpleNamespace(sha256=catalog))
    return value


def ledger_ddl():
    source = (ROOT / "tools" / "p09d_ammo_store.py").read_text(encoding="utf8")
    statements = [node.value for node in ast.walk(ast.parse(source))
                  if isinstance(node, ast.Constant) and isinstance(node.value, str)
                  and node.value.startswith("CREATE TABLE game_command_ledger(")]
    assert len(statements) == 1
    return statements[0]


def add_empty_reservations(connection):
    # Use actual store DDL, independently of migration pins.
    for file, table in (("p08b_battle_store.py", "p08b_reservation"),
                        ("p06t_mixed_store.py", "p06t_reservation"),
                        ("p06t_ammo_loss_store.py", "battle_ammo_loss_reservation")):
        source = (ROOT / "tools" / file).read_text(encoding="utf8")
        statements = [node.value for node in ast.walk(ast.parse(source))
                      if isinstance(node, ast.Constant) and isinstance(node.value, str)
                      and node.value.startswith("CREATE TABLE " + table + "(")]
        assert len(statements) == 1
        connection.execute(statements[0])


def add_empty_late(connection):
    # Use the real namespace creation, independently of migration pins.
    assert late_adapter(connection, m.OLD).namespace(create=True)


class Migration(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        self.db = self.dir / "game.sqlite"
        self.backups = self.dir / "backups"
        self.backups.mkdir()

    def test_backup_name_collision_never_overwrites_existing_data(self):
        make(self.db)
        source_before = self.db.read_bytes()
        real_open = m.os.open
        created = []

        def concurrent_create(path, flags, mode=0o777):
            target = Path(path)
            target.write_bytes(b"existing backup must survive")
            created.append(target)
            return real_open(path, flags, mode)

        with mock.patch.object(m.os, "open", side_effect=concurrent_create):
            with self.assertRaisesRegex(m.MigrationError, "backup name taken"):
                m.backup(self.db, self.backups, "apply")
        self.assertEqual(len(created), 1)
        self.assertEqual(created[0].read_bytes(), b"existing backup must survive")
        self.assertEqual(self.db.read_bytes(), source_before)

    def test_backup_failure_retains_reserved_file_without_changing_source(self):
        make(self.db)
        source_before = self.db.read_bytes()
        with mock.patch.object(m.sqlite3, "connect", side_effect=sqlite3.OperationalError("injected")):
            with self.assertRaisesRegex(m.MigrationError, "inspect reserved backup path"):
                m.backup(self.db, self.backups, "apply")
        files = list(self.backups.iterdir())
        self.assertEqual(len(files), 1)
        self.assertEqual(files[0].read_bytes(), b"")
        self.assertEqual(self.db.read_bytes(), source_before)

    def test_backup_uri_handles_special_directory_characters(self):
        make(self.db)
        directory = self.dir / "backup # %"
        directory.mkdir()
        copied = m.backup(self.db, directory, "apply")
        self.assertEqual(rows(copied), rows(self.db))

    def test_plan_is_read_only_and_lists_every_change(self):
        make(self.db)
        before = self.db.read_bytes()
        plan = m.plan(self.db, m.OLD, m.NEW)
        self.assertEqual(self.db.read_bytes(), before)
        self.assertEqual(plan["changes"], len(m.MARKER_TABLES) + 3)
        self.assertEqual({r["table"] for r in plan["json_rows"]}, {"p09e_research", "game_profiles", "game_snapshot"})

    def test_late_namespace_refuses_before_any_backup_or_database_write(self):
        # Include partial, empty, populated, and differently cased namespaces.
        cases = (("p08c_late_schema", False), ("p08c_late_result", True),
                 ("p08c_late_command", True), ("P08C_LATE_seal", True),
                 ("p08c_late_unknown", False), ("p08cXlateYother", False))
        for index, (table, populated) in enumerate(cases):
            with self.subTest(table=table):
                db = self.dir / ("late-%d.sqlite" % index)
                make(db)
                with closing(sqlite3.connect(str(db))) as c, c:
                    c.execute('CREATE TABLE "%s" (value TEXT)' % table)
                    if populated:
                        c.execute('INSERT INTO "%s" VALUES (?)' % table, ("historical record",))
                before = db.read_bytes()
                for action in (lambda: m.plan(db, m.OLD, m.NEW),
                               lambda: m.verify(db, m.OLD),
                               lambda: m.migrate(db, self.backups, m.OLD, m.NEW)):
                    with self.assertRaisesRegex(m.MigrationError, "late-results namespace requires"):
                        action()
                self.assertEqual(db.read_bytes(), before)
                self.assertEqual(list(self.backups.iterdir()), [])

    def test_empty_late_namespace_migrates_and_rolls_back(self):
        make(self.db)
        with closing(sqlite3.connect(str(self.db))) as c, c:
            add_empty_late(c)
            self.assertTrue(late_adapter(c, m.OLD).namespace())
        original = rows(self.db)
        self.assertIn("p08c_late_schema", [r["table"] for r in m.plan(self.db, m.OLD, m.NEW)["markers"]])
        m.migrate(self.db, self.backups, m.OLD, m.NEW)
        self.assertEqual(m.verify(self.db, m.NEW)["status"], "PASS")
        with closing(sqlite3.connect(str(self.db))) as c, c:
            self.assertTrue(late_adapter(c, m.NEW).namespace())
            self.assertEqual(c.execute("SELECT * FROM p08c_late_schema").fetchone(),
                             (late.SCHEMA, late.POLICY_SHA256, m.NEW))
        m.migrate(self.db, self.backups, m.NEW, m.OLD, label="rollback")
        self.assertEqual(m.verify(self.db, m.OLD)["status"], "PASS")
        with closing(sqlite3.connect(str(self.db))) as c, c:
            self.assertTrue(late_adapter(c, m.OLD).namespace())
        self.assertEqual(rows(self.db), original)

    def test_full_late_namespace_refuses_unknown_or_nonempty_state(self):
        cases = ("marker_version", "marker_policy", "marker_catalog", "extra_index",
                 "missing_index", "late_seal", "late_result", "late_command",
                 "p08b_reservation", "p06t_reservation", "battle_ammo_loss_reservation",
                 "finished_reservation", "missing_reservation", "wrong_reservation_schema")
        for index, case in enumerate(cases):
            with self.subTest(case=case):
                db = self.dir / ("late-full-%d.sqlite" % index)
                make(db)
                with closing(sqlite3.connect(str(db))) as c, c:
                    add_empty_late(c)
                    if case.startswith("marker_"):
                        col = {"marker_version": "version", "marker_policy": "policy_sha256",
                               "marker_catalog": "catalog_sha256"}[case]
                        c.execute("UPDATE p08c_late_schema SET " + col + "='unknown'")
                    elif case == "extra_index":
                        c.execute("CREATE INDEX extra_late ON p08c_late_seal(arena_id)")
                    elif case == "missing_index":
                        c.execute("DROP INDEX p08c_late_pending_idx")
                    elif case == "late_seal":
                        c.execute("INSERT INTO p08c_late_seal VALUES ('r','b','a','{}','h')")
                    elif case == "late_result":
                        c.execute("INSERT INTO p08c_late_result VALUES ('a','b','r','c','f','t',1,'s',1)")
                    elif case == "late_command":
                        c.execute("INSERT INTO p08c_late_command VALUES ('a','k','p','{}','r')")
                    elif case in m.RESERVATION_DDL_SHA256 or case == "finished_reservation":
                        table = "p06t_reservation" if case == "finished_reservation" else case
                        columns = c.execute("PRAGMA table_info(" + table + ")").fetchall()
                        names = [col[1] for col in columns]
                        values = [None if not col[3] else (1 if col[2] == "INTEGER" else "x") for col in columns]
                        if "status" in names:
                            values[names.index("status")] = "finished" if case == "finished_reservation" else "active"
                        if case == "finished_reservation":
                            for col in ("result_json", "result_sha256", "finished_revision"):
                                values[names.index(col)] = 1 if col == "finished_revision" else "x"
                        c.execute("INSERT INTO " + table + " VALUES (" + ",".join("?" for _ in values) + ")", values)
                    elif case == "missing_reservation":
                        c.execute("DROP TABLE p06t_reservation")
                    else:
                        c.execute("DROP TABLE p06t_reservation")
                        c.execute("CREATE TABLE p06t_reservation(status TEXT)")
                before = db.read_bytes()
                with self.assertRaisesRegex(m.MigrationError, "late-results namespace requires"):
                    m.migrate(db, self.backups, m.OLD, m.NEW)
                self.assertEqual(db.read_bytes(), before)
                self.assertEqual(list(self.backups.iterdir()), [])

    def test_no_late_namespace_refuses_reservation_history_or_unknown_schema(self):
        cases = ("p08b_reservation", "p06t_reservation", "battle_ammo_loss_reservation",
                 "finished_reservation", "missing_reservation", "wrong_reservation_schema")
        for index, case in enumerate(cases):
            with self.subTest(case=case):
                db = self.dir / ("no-late-%d.sqlite" % index)
                make(db)
                with closing(sqlite3.connect(str(db))) as c, c:
                    if case in ("missing_reservation", "wrong_reservation_schema"):
                        c.execute("DROP TABLE p06t_reservation")
                        if case == "wrong_reservation_schema":
                            c.execute("CREATE TABLE p06t_reservation(status TEXT)")
                    else:
                        table = "p06t_reservation" if case == "finished_reservation" else case
                        columns = c.execute("PRAGMA table_info(" + table + ")").fetchall()
                        names = [col[1] for col in columns]
                        values = [None if not col[3] else (1 if col[2] == "INTEGER" else "x") for col in columns]
                        if "status" in names:
                            values[names.index("status")] = "finished" if case == "finished_reservation" else "active"
                        if case == "finished_reservation":
                            for col in ("result_json", "result_sha256", "finished_revision"):
                                values[names.index(col)] = 1 if col == "finished_revision" else "x"
                        c.execute("INSERT INTO " + table + " VALUES (" + ",".join("?" for _ in values) + ")", values)
                before = db.read_bytes()
                for action in (lambda: m.plan(db, m.OLD, m.NEW),
                               lambda: m.verify(db, m.OLD),
                               lambda: m.migrate(db, self.backups, m.OLD, m.NEW)):
                    with self.assertRaisesRegex(m.MigrationError, "late-results namespace requires"):
                        action()
                self.assertEqual(db.read_bytes(), before)
                self.assertEqual(list(self.backups.iterdir()), [])

    def test_research_command_history_refuses_without_any_mutation(self):
        for index, operation in enumerate(("research", "buy_vehicle", "buy_module", "install", "buy_equip", "future")):
            with self.subTest(operation=operation):
                db = self.dir / ("research-ledger-%d.sqlite" % index)
                make(db)
                with closing(sqlite3.connect(str(db))) as c, c:
                    c.execute("INSERT INTO game_command_ledger VALUES (?,?,?,?,1,2,?,?)",
                              (ACCOUNT, "historic", "p09e-tank-module-research.v1:" + operation,
                               "historical-payload-sha", "historical-journal", "historical-journal-sha"))
                before = db.read_bytes()
                for action in (lambda: m.plan(db, m.OLD, m.NEW),
                               lambda: m.verify(db, m.OLD),
                               lambda: m.migrate(db, self.backups, m.OLD, m.NEW)):
                    with self.assertRaisesRegex(m.MigrationError, "research command history requires"):
                        action()
                self.assertEqual(db.read_bytes(), before)
                self.assertEqual(list(self.backups.iterdir()), [])

    def test_unknown_command_ledger_schema_refuses_without_mutation(self):
        make(self.db)
        with closing(sqlite3.connect(str(self.db))) as c, c:
            c.execute("DROP TABLE game_command_ledger")
            c.execute("CREATE TABLE game_command_ledger(command_type TEXT)")
        before = self.db.read_bytes()
        with self.assertRaisesRegex(m.MigrationError, "unknown command ledger schema"):
            m.migrate(self.db, self.backups, m.OLD, m.NEW)
        self.assertEqual(self.db.read_bytes(), before)
        self.assertEqual(list(self.backups.iterdir()), [])

    def test_command_ledger_blob_or_unknown_objects_refuse(self):
        for index, case in enumerate(("blob", "extra_index", "extra_trigger")):
            with self.subTest(case=case):
                db = self.dir / ("ledger-invalid-%d.sqlite" % index)
                make(db)
                with closing(sqlite3.connect(str(db))) as c, c:
                    if case == "blob":
                        c.execute("UPDATE game_command_ledger SET command_type=?", (b"p09e-tank-module-research.v1:research",))
                    elif case == "extra_index":
                        c.execute("CREATE INDEX ledger_extra ON game_command_ledger(command_type)")
                    else:
                        c.execute("CREATE TRIGGER ledger_extra BEFORE INSERT ON game_command_ledger BEGIN SELECT 1; END")
                before = db.read_bytes()
                with self.assertRaisesRegex(m.MigrationError, "unknown command ledger"):
                    m.migrate(db, self.backups, m.OLD, m.NEW)
                self.assertEqual(db.read_bytes(), before)
                self.assertEqual(list(self.backups.iterdir()), [])

    def test_verify_reports_migration_scope_and_refuses_new_research_history(self):
        make(self.db)
        m.migrate(self.db, self.backups, m.OLD, m.NEW)
        self.assertEqual(m.verify(self.db, m.NEW)["scope"], "migration-preconditions-and-markers-not-store-health")
        with closing(sqlite3.connect(str(self.db))) as c, c:
            c.execute("INSERT INTO game_command_ledger VALUES (?,?,?,?,1,2,?,?)",
                      (ACCOUNT, "current", "p09e-tank-module-research.v1:research", "sha", "journal", "hash"))
        with self.assertRaisesRegex(m.MigrationError, "research command history requires"):
            m.verify(self.db, m.NEW)

    def test_real_owner_altered_ledger_schema_is_admitted(self):
        make(self.db)
        with GameProfileStore() as owner:
            owner.initialize()
            owner.connection.execute("ALTER TABLE game_command_ledger ADD COLUMN p09c_result_sha256 TEXT")
            ddl = owner.connection.execute("SELECT sql FROM sqlite_master WHERE name='game_command_ledger'").fetchone()[0]
        with closing(sqlite3.connect(str(self.db))) as c, c:
            c.execute("DROP TABLE game_command_ledger")
            c.execute(ddl)
        self.assertEqual(m.migrate(self.db, self.backups, m.OLD, m.NEW)["status"], "PASS")

    def test_research_history_created_after_plan_refuses_under_lock(self):
        make(self.db)
        original = rows(self.db)
        real_backup = m.backup

        def write_after_plan(db, backup_dir, label):
            saved = real_backup(db, backup_dir, label)
            with closing(sqlite3.connect(str(db))) as c, c:
                c.execute("INSERT INTO game_command_ledger VALUES (?,?,?,?,1,2,?,?)",
                          (ACCOUNT, "concurrent", "p09e-tank-module-research.v1:research",
                           "old-payload", "old-journal", "old-journal-sha"))
            return saved

        with mock.patch.object(m, "backup", side_effect=write_after_plan):
            with self.assertRaisesRegex(m.MigrationError, "research command history requires"):
                m.migrate(self.db, self.backups, m.OLD, m.NEW)
        after = rows(self.db)
        after_ledger = after.pop("game_command_ledger")
        original_ledger = original.pop("game_command_ledger")
        self.assertEqual(after, original)
        self.assertEqual(len(after_ledger), len(original_ledger) + 1)
        self.assertTrue(all(item in after_ledger for item in original_ledger))
        self.assertEqual(json.loads(next(self.backups.glob("*.receipt.json")).read_text())["status"], "PENDING")

    def test_empty_late_marker_rolls_back_when_fixture_move_fails(self):
        make(self.db)
        with closing(sqlite3.connect(str(self.db))) as c, c:
            add_empty_late(c)
        original = rows(self.db)
        root = self.dir / "fixtures"
        cache = root / ACCOUNT / "p09d-r3"
        cache.mkdir(parents=True)
        (cache / "manifest.json").write_text(m.OLD, encoding="ascii")
        with mock.patch.object(Path, "rename", side_effect=OSError("injected failure")):
            with self.assertRaisesRegex(m.MigrationError, "PENDING receipt"):
                m.migrate(self.db, self.backups, m.OLD, m.NEW, root)
        self.assertEqual(rows(self.db), original)
        with closing(sqlite3.connect(str(self.db))) as c, c:
            self.assertTrue(late_adapter(c, m.OLD).namespace())
        self.assertEqual(m.verify(self.db, m.OLD)["status"], "PASS")

    def test_late_namespace_created_after_plan_refuses_under_exclusive_lock(self):
        make(self.db)
        original = rows(self.db)
        real_backup = m.backup

        def create_late_after_plan(db, backup_dir, label):
            saved = real_backup(db, backup_dir, label)
            with closing(sqlite3.connect(str(db))) as c, c:
                c.execute("CREATE TABLE p08c_late_schema (version TEXT)")
                c.execute("INSERT INTO p08c_late_schema VALUES ('concurrent')")
            return saved

        with mock.patch.object(m, "backup", side_effect=create_late_after_plan):
            with self.assertRaisesRegex(m.MigrationError, "late-results namespace requires"):
                m.migrate(self.db, self.backups, m.OLD, m.NEW)
        after = rows(self.db)
        self.assertEqual(after.pop("p08c_late_schema"), ["('concurrent',)"])
        self.assertEqual(after, original)
        receipt = next(self.backups.glob("*.receipt.json"))
        self.assertEqual(json.loads(receipt.read_text())["status"], "PENDING")

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
