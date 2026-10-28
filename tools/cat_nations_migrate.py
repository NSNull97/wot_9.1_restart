"""CAT-NATIONS: move a stand game database between research catalogue hashes.

The research catalogue SHA-256 changed when its nation order became the
client's (b6baecd2... -> 1f6b20d1...). Stores refuse a database whose
markers name another catalogue, so a stand database needs this one-off,
reversible rewrite. Nothing else in the rows changes: research state refers to
items by semantic ID (``vehicle:uk:...``), never by compact ID.

Rewritten (one transaction, exact ``catalog_sha256`` fields only):
- ``catalog_sha256`` of p09e_schema, p08b_schema, p04m_schema, p06t_schema,
  battle_ammo_loss_schema;
- ``p09e_research.state_json`` (+ ``state_sha256``),
  ``game_profiles.profile_json`` (``research.catalog_sha256``),
  ``game_snapshot.snapshot_json`` (+ ``snapshot_sha256``).
Kept as history: ``game_command_ledger`` results and payload hashes, the
immutable ``p04m_owner`` activation baseline (trigger-protected).
Fixture caches of the current revision that name the old hash are moved aside
(``<dir>.before-cat-nations``) so workers rebuild them; ``rollback`` moves them back.

Commands (``--db`` is a developer path; the tool never guesses a stand):
  plan     --db DB [--fixture-root F] [--to new|old]   dry run, read-only
  apply    --db DB --backup-dir B [--fixture-root F]   backup, then old -> new
  rollback --db DB --backup-dir B [--fixture-root F]   backup, then new -> old
  verify   --db DB --expect new|old                    integrity + markers
Every write first takes an SQLite online backup into a fresh file under
``--backup-dir`` and records a receipt next to it. Services must be stopped:
the rewrite runs under ``BEGIN EXCLUSIVE`` and fails if the file is busy.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
from pathlib import Path
import sqlite3
import sys

OLD = "b6baecd204444d1e894253fa6c19c61478993b8ae87c71373633989d3a8ee460"
NEW = "1f6b20d1ba564e00186fed77a3da74c3bd9b135f0db30ffdef740fd5888ced80"
HASHES = {"old": OLD, "new": NEW}
SCHEMA = "cat-nations-db-migration.v1"
MARKER_TABLES = ("p09e_schema", "p08b_schema", "p04m_schema", "p06t_schema", "battle_ammo_loss_schema")
# (table, key column, JSON column, SHA column of exact JSON text or None)
JSON_ROWS = (("p09e_research", "account_id", "state_json", "state_sha256"),
             ("game_profiles", "account_id", "profile_json", None),
             ("game_snapshot", "account_id", "snapshot_json", "snapshot_sha256"))
MAX_DB_BYTES = 512 * 1024 * 1024
MAX_JSON_BYTES = 4 * 1024 * 1024
MAX_ROWS = 4096
MAX_FIXTURE_FILES = 200000
MOVED_SUFFIX = ".before-cat-nations"


class MigrationError(ValueError):
    pass


def require(ok, message):
    if not ok:
        raise MigrationError(message)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _db(path):
    path = Path(path)
    require(path.is_file() and not path.is_symlink(), "database file required: " + str(path))
    require(0 < path.stat().st_size <= MAX_DB_BYTES, "database size bound")
    return path.resolve()


def _replace(value, source, target, depth=0):
    """Replace exact ``catalog_sha256`` fields equal to ``source``; return (value, count)."""
    require(depth <= 32, "JSON depth bound")
    if isinstance(value, dict):
        count, out = 0, {}
        for key, item in value.items():
            if key == "catalog_sha256" and item == source:
                out[key], count = target, count + 1
            else:
                out[key], n = _replace(item, source, target, depth + 1)
                count += n
        return out, count
    if isinstance(value, list):
        rows = [_replace(item, source, target, depth + 1) for item in value]
        return [r[0] for r in rows], sum(r[1] for r in rows)
    return value, 0


def _tables(connection):
    return {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def survey(connection, source, target):
    """Read-only: every change the rewrite would make, or a refusal."""
    tables = _tables(connection)
    markers, rows = [], []
    for table in MARKER_TABLES:
        if table not in tables:
            continue
        values = [r[0] for r in connection.execute("SELECT catalog_sha256 FROM " + table)]
        require(len(values) == 1, table + ": one schema marker row expected")
        require(values[0] in (source, target), table + ": unknown catalogue " + values[0])
        markers.append(dict(table=table, current=values[0], change=values[0] == source))
    for table, key, column, digest in JSON_ROWS:
        if table not in tables:
            continue
        select = "SELECT %s,%s%s FROM %s" % (key, column, "," + digest if digest else "", table)
        found = connection.execute(select).fetchall()
        require(len(found) <= MAX_ROWS, table + ": row bound")
        for record in found:
            text = record[1]
            require(type(text) is str and len(text) <= MAX_JSON_BYTES, table + ": JSON bound")
            require(digest is None or sha(text.encode("ascii")) == record[2], table + ": stored SHA differs before migration")
            value = json.loads(text)
            require(canonical(value) == text, table + ": stored JSON is not canonical; refusing to rewrite")
            new_value, count = _replace(value, source, target)
            if count:
                new_text = canonical(new_value)
                rows.append(dict(table=table, key=record[0], fields=count, column=column, digest=digest,
                                 old_sha256=sha(text.encode("ascii")), new_text=new_text,
                                 new_sha256=sha(new_text.encode("ascii"))))
    return markers, rows


def fixture_dirs(fixture_root, connection, source, moved=False):
    """Fixture cache dirs of each account's current revision that name ``source``."""
    if fixture_root is None:
        return []
    root = Path(fixture_root)
    require(root.is_dir() and not root.is_symlink(), "fixture root must be a directory")
    revisions = dict(connection.execute("SELECT account_id,revision FROM game_snapshot").fetchall())
    found, files = [], 0
    for account, revision in sorted(revisions.items()):
        name = "p09d-r%d" % revision + (MOVED_SUFFIX if moved else "")
        for path in sorted(root.glob("**/" + account + "/" + name)):
            require(not path.is_symlink() and path.is_dir(), "fixture cache must be a plain directory: " + str(path))
            hit = False
            for member in path.rglob("*"):
                files += 1
                require(files <= MAX_FIXTURE_FILES and not member.is_symlink(), "fixture file bound/link")
                if member.is_file() and member.stat().st_size <= MAX_JSON_BYTES and source.encode() in member.read_bytes():
                    hit = True
            if hit or moved:
                found.append(path)
    return found


def plan(db, source, target, fixture_root=None):
    connection = sqlite3.connect("file:%s?mode=ro" % _db(db).as_posix(), uri=True)
    try:
        markers, rows = survey(connection, source, target)
        fixtures = fixture_dirs(fixture_root, connection, source)
    finally:
        connection.close()
    return dict(schema=SCHEMA, command="plan", database=str(_db(db)), source=source, target=target,
                markers=markers, json_rows=[{k: r[k] for k in ("table", "key", "fields", "old_sha256", "new_sha256")}
                                            for r in rows],
                fixture_dirs=[str(p) for p in fixtures],
                untouched=["game_command_ledger (history)", "p04m_owner (immutable baseline)"],
                changes=sum(m["change"] for m in markers) + len(rows))


def backup(db, backup_dir, label):
    backup_dir = Path(backup_dir)
    require(backup_dir.is_dir() and not backup_dir.is_symlink(), "backup dir must exist")
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    target = backup_dir / ("%s.before-cat-nations-%s-%s.sqlite" % (Path(db).stem, label, stamp))
    require(not target.exists(), "backup name taken: " + str(target))
    source = sqlite3.connect(str(_db(db)))
    copy = sqlite3.connect(str(target))
    try:
        source.backup(copy)
    finally:
        copy.close()
        source.close()
    return target


def migrate(db, backup_dir, source, target, fixture_root=None, label="apply"):
    before = plan(db, source, target, fixture_root)
    require(before["changes"] > 0 or before["fixture_dirs"], "nothing to migrate (already at target?)")
    saved = backup(db, backup_dir, label)
    connection = sqlite3.connect(str(_db(db)), isolation_level=None, timeout=1)
    try:
        connection.execute("BEGIN EXCLUSIVE")
        try:
            markers, rows = survey(connection, source, target)
            for marker in markers:
                if marker["change"]:
                    done = connection.execute("UPDATE %s SET catalog_sha256=? WHERE catalog_sha256=?" % marker["table"],
                                              (target, source)).rowcount
                    require(done == 1, marker["table"] + ": marker update")
            for row in rows:
                sets = "%s=?" % row["column"] + (",%s=?" % row["digest"] if row["digest"] else "")
                args = [row["new_text"]] + ([row["new_sha256"]] if row["digest"] else [])
                done = connection.execute("UPDATE %s SET %s WHERE account_id=?" % (row["table"], sets),
                                          args + [row["key"]]).rowcount
                require(done == 1, row["table"] + ": row update")
            check = verify_connection(connection, target)
            connection.execute("COMMIT")
        except BaseException:
            connection.execute("ROLLBACK")
            raise
    finally:
        connection.close()
    moved = []
    if fixture_root is not None:
        ro = sqlite3.connect("file:%s?mode=ro" % _db(db).as_posix(), uri=True)
        try:
            if label == "apply":
                for path in fixture_dirs(fixture_root, ro, source):
                    destination = path.with_name(path.name + MOVED_SUFFIX)
                    require(not destination.exists(), "moved fixture name taken: " + str(destination))
                    path.rename(destination)
                    moved.append([str(path), str(destination)])
            else:
                for path in fixture_dirs(fixture_root, ro, source, moved=True):
                    destination = path.with_name(path.name[:-len(MOVED_SUFFIX)])
                    require(not destination.exists(), "fixture dir exists, will not overwrite: " + str(destination))
                    path.rename(destination)
                    moved.append([str(path), str(destination)])
        finally:
            ro.close()
    receipt = dict(schema=SCHEMA, command=label, status="PASS", database=str(_db(db)), source=source, target=target,
                   backup=str(saved), backup_sha256=sha(saved.read_bytes()), plan=before, verify=check, fixtures_moved=moved)
    path = saved.with_suffix(".receipt.json")
    with path.open("x", encoding="ascii") as stream:
        stream.write(canonical(receipt) + "\n")
    return dict(receipt, receipt=str(path))


def verify_connection(connection, expected):
    other = OLD if expected == NEW else NEW
    require(connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok", "integrity_check")
    markers, rows = survey(connection, other, expected)
    require(all(m["current"] == expected for m in markers), "a schema marker is not at the expected catalogue")
    require(not rows, "a JSON row still names the other catalogue")
    counts = {}
    tables = _tables(connection)
    for table, _, column, _ in JSON_ROWS:
        if table in tables:
            counts[table] = sum(1 for r in connection.execute("SELECT %s FROM %s" % (column, table))
                                if _replace(json.loads(r[0]), expected, expected)[1])
    return dict(expected=expected, markers=[m["table"] for m in markers], rows_naming_expected=counts)


def verify(db, expected):
    connection = sqlite3.connect("file:%s?mode=ro" % _db(db).as_posix(), uri=True)
    try:
        return dict(schema=SCHEMA, command="verify", status="PASS", database=str(_db(db)),
                    **verify_connection(connection, expected))
    finally:
        connection.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("plan")
    p.add_argument("--db", required=True)
    p.add_argument("--fixture-root")
    p.add_argument("--to", choices=("new", "old"), default="new")
    for name in ("apply", "rollback"):
        a = sub.add_parser(name)
        a.add_argument("--db", required=True)
        a.add_argument("--backup-dir", required=True)
        a.add_argument("--fixture-root")
    v = sub.add_parser("verify")
    v.add_argument("--db", required=True)
    v.add_argument("--expect", choices=("new", "old"), required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "plan":
            target = HASHES[args.to]
            result = plan(args.db, OLD if target == NEW else NEW, target, args.fixture_root)
        elif args.command == "apply":
            result = migrate(args.db, args.backup_dir, OLD, NEW, args.fixture_root, "apply")
        elif args.command == "rollback":
            result = migrate(args.db, args.backup_dir, NEW, OLD, args.fixture_root, "rollback")
        else:
            result = verify(args.db, HASHES[args.expect])
        print(json.dumps(result, sort_keys=True, indent=1))
        return 0
    except (OSError, ValueError, sqlite3.Error) as error:
        print(json.dumps(dict(schema=SCHEMA, status="FAIL", reason=str(error))))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
