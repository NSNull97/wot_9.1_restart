"""CAT-NATIONS test-input re-stamps: seed copies and P04M writer fixtures."""
import hashlib
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "tests" / "helpers"), str(ROOT / "tools"), str(ROOT / "tests")]
import cat_nations_migrate as m
import cat_nations_test_restamp as r
import cat_nations_writer_fixture_restamp as w
from test_cat_nations_migrate import make, rows


class SeedCopyRestampTests(unittest.TestCase):
    def copy(self, base):
        path = Path(base) / "test-runs" / "case" / "run-1" / "game.sqlite"
        path.parent.mkdir(parents=True)
        make(path)
        return path

    def test_rewrites_markers_and_rows_keeps_ledger_and_refuses_reuse(self):
        with tempfile.TemporaryDirectory() as base:
            path = self.copy(base)
            before = rows(path)
            receipt = r.restamp_copy(path)
            self.assertEqual(receipt["markers"], list(m.MARKER_TABLES))
            self.assertEqual(receipt["json_rows"], 3)
            after = rows(path)
            self.assertEqual(after["game_command_ledger"], before["game_command_ledger"])
            self.assertTrue(all(m.OLD not in "".join(after[t]) for t in after if t != "game_command_ledger"))
            self.assertEqual(m.verify(path, m.NEW)["status"], "PASS")
            again = r.restamp_copy(path)
            self.assertEqual((again["markers"], again["json_rows"]), ([], 0))

    def test_refuses_late_namespace_unknown_marker_and_foreign_path(self):
        with tempfile.TemporaryDirectory() as base:
            path = self.copy(base)
            with closing(sqlite3.connect(path)) as c:
                c.execute("CREATE TABLE p08c_late_schema(version TEXT)")
                c.commit()
            before = rows(path)
            with self.assertRaisesRegex(m.MigrationError, "late-results"):
                r.restamp_copy(path)
            self.assertEqual(rows(path), before)
        with tempfile.TemporaryDirectory() as base:
            path = self.copy(base)
            with closing(sqlite3.connect(path)) as c:
                c.execute("UPDATE p04m_schema SET catalog_sha256=?", ("a" * 64,))
                c.commit()
            before = rows(path)
            with self.assertRaisesRegex(m.MigrationError, "unknown catalogue"):
                r.restamp_copy(path)
            self.assertEqual(rows(path), before)
        with tempfile.TemporaryDirectory() as base:
            path = Path(base) / "game.sqlite"
            make(path)
            with self.assertRaisesRegex(m.MigrationError, "fresh test-runs copy"):
                r.restamp_copy(path)


class WriterFixtureRestampTests(unittest.TestCase):
    def test_hash_chain_converges_and_unrelated_members_stay_identical(self):
        sha = lambda raw: hashlib.sha256(raw).hexdigest()
        research = b'{"catalog_sha256":"' + m.OLD.encode() + b'"}'
        manifest = b'{"research":"' + sha(research).encode() + b'"}'
        receipt = b'{"manifest":"' + sha(manifest).encode() + b'","state":"' + sha(b"state").encode() + b'"}'
        files = {"research.json": research, "manifest.json": manifest, "receipt.json": receipt, "state.bin": b"state"}
        out, mapping = w.restamp(files)
        self.assertEqual(out["state.bin"], b"state")
        self.assertEqual(out["research.json"], research.replace(m.OLD.encode(), m.NEW.encode()))
        self.assertIn(sha(out["research.json"]).encode(), out["manifest.json"])
        self.assertIn(sha(out["manifest.json"]).encode(), out["receipt.json"])
        self.assertIn(sha(b"state").encode(), out["receipt.json"])
        self.assertEqual(len(mapping), 4)
        self.assertFalse(any(m.OLD.encode() in v or sha(files[k]).encode() in b"".join(out.values())
                             for k, v in out.items() if out[k] != files[k]))


if __name__ == "__main__":
    unittest.main()
