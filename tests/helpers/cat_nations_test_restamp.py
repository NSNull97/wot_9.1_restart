"""CAT-NATIONS, TEST copies only: re-stamp a fresh backup of a pinned pre-CAT seed.

The composition seeds (``p06t-owned01/seed01``, ``p10b-selection-http01/seed01``)
were written under research catalogue ``b6baecd2...``; current stores refuse
them. The source DB stays pinned and read-only; each seed helper backs it up
into its own fresh ``local/test-runs/.../run-*/game.sqlite`` and calls
``restamp_copy`` on that copy before opening any store.

The rewrite is the one ``tools/cat_nations_migrate.py`` performs (same marker
tables, same JSON rows, same canonical/SHA checks, ``game_command_ledger`` and
the immutable ``p04m_owner`` baseline kept as history). Unlike the stand
migrator it does not refuse finished reservation rows or P09E research command
history: those guards protect retries of historical commands on a live stand,
and no composition test retries a source command (a retry would fail closed on
its catalogue-bound payload hash). A ``p08c_late_*`` namespace, a missing or
unknown marker, or a marker table absent from the copy is still refused.
This is not a stand migration and does not prove one.
"""
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from cat_nations_migrate import JSON_ROWS, MARKER_TABLES, NEW, OLD, _replace, canonical, require, sha  # noqa: E402

SCHEMA = "cat-nations-test-restamp.v1"
# battle_ammo_loss_schema is created later by the seed's own activation, with the current catalogue.
PRESEED_MARKERS = tuple(t for t in MARKER_TABLES if t != "battle_ammo_loss_schema")


def restamp_copy(database):
    database = Path(database)
    require(database.is_file() and not database.is_symlink() and database.name == "game.sqlite"
            and database.parent.name.startswith("run-") and "test-runs" in database.parts,
            "fresh test-runs copy required")
    with closing(sqlite3.connect(str(database), isolation_level=None, timeout=1)) as db:
        db.execute("BEGIN EXCLUSIVE")
        try:
            tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            require(not any(t.startswith("p08c_late_") for t in tables), "late-results namespace in source copy")
            require(set(PRESEED_MARKERS) <= tables, "missing marker tables")
            markers = list(PRESEED_MARKERS) + [t for t in ("battle_ammo_loss_schema",) if t in tables]
            changed = []
            for table in markers:
                values = [r[0] for r in db.execute("SELECT catalog_sha256 FROM " + table)]
                require(len(values) == 1 and values[0] in (OLD, NEW), table + ": unknown catalogue marker")
                if values[0] == OLD:
                    require(db.execute("UPDATE %s SET catalog_sha256=? WHERE catalog_sha256=?" % table, (NEW, OLD)).rowcount == 1,
                            table + ": marker update")
                    changed.append(table)
            rows = 0
            for table, key, column, digest in JSON_ROWS:
                found = db.execute("SELECT %s,%s%s FROM %s" % (key, column, "," + digest if digest else "", table)).fetchall()
                require(0 < len(found) <= 64, table + ": row bound")
                for record in found:
                    text = record[1]
                    require(type(text) is str and (digest is None or sha(text.encode("ascii")) == record[2]), table + ": stored SHA")
                    value = json.loads(text)
                    require(canonical(value) == text, table + ": stored JSON is not canonical")
                    new_value, count = _replace(value, OLD, NEW, table)
                    if count:
                        new_text = canonical(new_value)
                        sets = column + "=?" + ("," + digest + "=?" if digest else "")
                        args = [new_text] + ([sha(new_text.encode("ascii"))] if digest else [])
                        require(db.execute("UPDATE %s SET %s WHERE %s=?" % (table, sets, key), args + [record[0]]).rowcount == 1,
                                table + ": row update")
                        rows += 1
            for table in markers:
                require(db.execute("SELECT catalog_sha256 FROM " + table).fetchone()[0] == NEW, table + ": marker after")
            require(db.execute("PRAGMA integrity_check").fetchone()[0] == "ok", "integrity_check")
            db.execute("COMMIT")
        except BaseException:
            db.execute("ROLLBACK")
            raise
    return dict(schema=SCHEMA, source=OLD, target=NEW, markers=changed, json_rows=rows,
                untouched=["game_command_ledger (history)", "p04m_owner (immutable baseline)"])
