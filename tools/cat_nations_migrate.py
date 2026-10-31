"""CAT-NATIONS: move a stand game database between research catalogue hashes.

The research catalogue SHA-256 changed when its nation order became the
client's (b6baecd2... -> 1f6b20d1...). Stores refuse a database whose
markers name another catalogue, so a stand database needs this one-off,
reversible rewrite. Nothing else in the rows changes: research state refers to
items by semantic ID (``vehicle:uk:...``), never by compact ID.

Rewritten (one transaction, exact ``catalog_sha256`` fields only):
- ``catalog_sha256`` of p09e_schema, p08b_schema, p04m_schema, p06t_schema,
  battle_ammo_loss_schema;
- ``p08c_late_schema.catalog_sha256`` only when its pinned namespace and all
  related reservation tables are present and entirely empty;
- ``p09e_research.state_json`` (+ ``state_sha256``),
  ``game_profiles.profile_json`` (``research.catalog_sha256``),
  ``game_snapshot.snapshot_json`` (+ ``snapshot_sha256``).
Kept as history: ``game_command_ledger`` results and payload hashes, the
immutable ``p04m_owner`` activation baseline (trigger-protected).
Existing late-result or reservation history is not migrated: such databases
are refused before a backup or rewrite, even if the lazy late namespace does
not yet exist. Historical research commands are also refused because their
replay payload and journal are bound to the source catalog.
Fixture caches of the current revision that name the old hash are moved aside
(``<dir>.before-cat-nations``) so workers rebuild them; ``rollback`` moves them back.

Commands (``--db`` is a developer path; the tool never guesses a stand):
  plan     --db DB [--fixture-root F] [--to new|old]   dry run, read-only
  apply    --db DB --backup-dir B [--fixture-root F]   backup, then old -> new
  rollback --db DB --backup-dir B [--fixture-root F]   backup, then new -> old
  verify   --db DB --expect new|old                    migration-specific checks
The verify command checks this tool's migration preconditions and expected
markers; it is not a health check or a proof of live-store compatibility. It
intentionally refuses databases containing unsupported historical records.
Every write first takes an SQLite online backup and records and flushes a PENDING
receipt with a complete fixture move plan. Services must be stopped: the backup
and database/file changes are not one atomic operation and the exclusive lock
cannot prove services were stopped. Fixture moves happen before SQLite commit;
ordinary failures attempt rollback of both. A crash or failure while writing the
final PASS receipt leaves PENDING: stop services, inspect the database and every
fixture path, restore the backup and original fixture paths without overwriting,
and retain the receipt. Do not retry blindly. Concurrent changes are unsupported.
"""
from __future__ import annotations

import argparse
import datetime
import copy
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys

OLD = "b6baecd204444d1e894253fa6c19c61478993b8ae87c71373633989d3a8ee460"
NEW = "1f6b20d1ba564e00186fed77a3da74c3bd9b135f0db30ffdef740fd5888ced80"
HASHES = {"old": OLD, "new": NEW}
SCHEMA = "cat-nations-db-migration.v1"
MARKER_TABLES = ("p09e_schema", "p08b_schema", "p04m_schema", "p06t_schema", "battle_ammo_loss_schema")
LATE_SCHEMA = "p08c-late-results.v1"
LATE_POLICY = "f6ae697fb920b9359a2cb0375aa1fd68538a183fab1c8f136772c703de6abe04"
# SHA-256 of the ordered sqlite_master objects created by the pinned
# LateResults.namespace() implementation, serialized with canonical().
LATE_OBJECTS_SHA256 = "5995ab535a48b50a8a16b7a26fdf8bc2c19f03fcbb09b0ffa711a348d5f4e0dd"
# Real owner table + P09C ALTER, and independently initialized P09D table.
# Pin every table/index object so extra triggers or indexes are not trusted.
LEDGER_OBJECTS_SHA256 = frozenset((
    "2f2082880eb8b68a2e3ee245eb2f9926296a321a9da4ace2c318d22e626427dc",
    "74cabe1c849cc40c6c915452b155a33568db6a65cd1d327d237f71940621e60c",
))
RESERVATION_DDL_SHA256 = {
    "p08b_reservation": "deab4b73d42c2f3bbeab692736aa1d3ca15d1f06b7ba3e63f9e1aa4a107c1b7b",
    "p06t_reservation": "c333dfcaf8f5bb4b92051b52f7a96b99bcd311d621bd28e311d7367dadbb2a91",
    "battle_ammo_loss_reservation": "33655b466b3adc0c38752ce3bb36fddcfc5678f1724cc380536eda2a32b735b3",
}
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


def _replace(value, source, target, table):
    """Rewrite the research catalogue only; ammo catalogues have distinct hashes."""
    require(type(value) is dict, table + ": JSON object required")
    out = copy.deepcopy(value)
    research = out if table == "p09e_research" else out.get("research")
    require(type(research) is dict, table + ": missing research object")
    item = research.get("catalog_sha256")
    require(item in (source, target), table + ": unknown catalogue in research JSON: " + repr(item))
    if item == source:
        research["catalog_sha256"] = target
        return out, 1
    return out, 0


def _tables(connection):
    return {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def survey(connection, source, target):
    """Read-only: every change the rewrite would make, or a refusal."""
    tables = _tables(connection)
    required = set(MARKER_TABLES) | {table for table, _, _, _ in JSON_ROWS}
    require(required <= tables, "missing required tables: " + ", ".join(sorted(required - tables)))
    # Match the namespace's SQL LIKE lookup (including wildcard underscores),
    # and also reject unexpected indexes, triggers, and views on its tables.
    objects = connection.execute("SELECT type,name,tbl_name,sql FROM sqlite_master "
        "WHERE name LIKE 'p08c_late_%' OR tbl_name LIKE 'p08c_late_%' ORDER BY type,name").fetchall()
    late_marker = None
    if objects:
        require(sha(canonical(objects).encode("ascii")) == LATE_OBJECTS_SHA256,
                "late-results namespace requires a separately validated migration: unknown schema objects")
        marker = connection.execute("SELECT version,policy_sha256,catalog_sha256 FROM p08c_late_schema").fetchall()
        require(len(marker) == 1 and marker[0][0:2] == (LATE_SCHEMA, LATE_POLICY)
                and marker[0][2] in (source, target),
                "late-results namespace requires a separately validated migration: unknown marker")
        for table in ("p08c_late_seal", "p08c_late_result", "p08c_late_command"):
            require(connection.execute("SELECT 1 FROM " + table + " LIMIT 1").fetchone() is None,
                    "late-results namespace requires a separately validated migration: history present")
        late_marker = dict(table="p08c_late_schema", current=marker[0][2], change=marker[0][2] == source)
    # The late namespace is lazy: a finished early-release reservation can
    # still await its first late seal even when no namespace has been created.
    # Until history compatibility is established, require all related
    # reservation tables to exist with their pinned schema and no rows.
    for table, digest in RESERVATION_DDL_SHA256.items():
        ddl = connection.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
        require(ddl is not None and type(ddl[0]) is str and sha(ddl[0].encode("utf8")) == digest,
                "late-results namespace requires a separately validated migration: unknown reservation schema " + table)
        require(connection.execute("SELECT 1 FROM " + table + " LIMIT 1").fetchone() is None,
                "late-results namespace requires a separately validated migration: reservation history " + table)
    # P09E binds the catalogue SHA into each command's payload hash and replays
    # its journal through the catalogue. Repointing the current marker without
    # a versioned historical replay contract breaks legitimate retries.
    ledger_objects = connection.execute("SELECT type,name,tbl_name,sql FROM sqlite_master "
        "WHERE name='game_command_ledger' OR tbl_name='game_command_ledger' ORDER BY type,name").fetchall()
    require(sha(canonical(ledger_objects).encode("ascii")) in LEDGER_OBJECTS_SHA256,
            "unknown command ledger schema")
    require(connection.execute("SELECT 1 FROM game_command_ledger WHERE typeof(command_type) != 'text' LIMIT 1").fetchone() is None,
            "unknown command ledger command type")
    require(connection.execute("SELECT 1 FROM game_command_ledger WHERE command_type LIKE ? LIMIT 1",
                               ("p09e-tank-module-research.v1:%",)).fetchone() is None,
            "research command history requires a separately validated migration")
    markers, rows = [], []
    for table in MARKER_TABLES:
        values = [r[0] for r in connection.execute("SELECT catalog_sha256 FROM " + table)]
        require(len(values) == 1, table + ": one schema marker row expected")
        require(values[0] in (source, target), table + ": unknown catalogue " + values[0])
        markers.append(dict(table=table, current=values[0], change=values[0] == source))
    if late_marker is not None:
        markers.append(late_marker)
    for table, key, column, digest in JSON_ROWS:
        select = "SELECT %s,%s%s FROM %s" % (key, column, "," + digest if digest else "", table)
        found = connection.execute(select).fetchall()
        require(0 < len(found) <= MAX_ROWS, table + ": empty table or row bound")
        for record in found:
            text = record[1]
            require(type(text) is str and len(text) <= MAX_JSON_BYTES, table + ": JSON bound")
            require(digest is None or sha(text.encode("ascii")) == record[2], table + ": stored SHA differs before migration")
            value = json.loads(text)
            require(canonical(value) == text, table + ": stored JSON is not canonical; refusing to rewrite")
            new_value, count = _replace(value, source, target, table)
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
    database = _db(db)
    try:
        # CREATE_NEW claims this name atomically; never open a pre-existing backup.
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0), 0o600)
    except FileExistsError as error:
        raise MigrationError("backup name taken: " + str(target)) from error
    except OSError as error:
        raise MigrationError("cannot reserve backup name: " + str(target)) from error
    try:
        os.close(fd)
    except OSError as error:
        raise MigrationError("cannot close reserved backup; inspect path: " + str(target)) from error
    try:
        source = sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)
        try:
            # Do not recreate a missing reserved path; retain partial backups on failure.
            copy = sqlite3.connect(target.absolute().as_uri() + "?mode=rw", uri=True)
            try:
                source.backup(copy)
            finally:
                copy.close()
        finally:
            source.close()
    except (OSError, sqlite3.Error) as error:
        raise MigrationError("backup failed; inspect reserved backup path: " + str(target)) from error
    return target


def _write_receipt(path, receipt, *, create=False):
    # Flush the PENDING receipt before mutation; it describes recovery after interruption.
    with path.open("x" if create else "w", encoding="ascii") as stream:
        stream.write(canonical(receipt) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def migrate(db, backup_dir, source, target, fixture_root=None, label="apply"):
    before = plan(db, source, target, fixture_root)
    # For rollback, plan() sees ordinary caches, but recovery uses the moved caches.
    ro = sqlite3.connect("file:%s?mode=ro" % _db(db).as_posix(), uri=True)
    try:
        paths = fixture_dirs(fixture_root, ro, source, moved=(label == "rollback"))
    finally:
        ro.close()
    moves = []
    for path in paths:
        name = path.name[:-len(MOVED_SUFFIX)] if label == "rollback" else path.name + MOVED_SUFFIX
        destination = path.with_name(name)
        require(not destination.exists(), "fixture destination exists: " + str(destination))
        moves.append((path, destination))
    require(before["changes"] > 0 or moves, "nothing to migrate (already at target?)")
    saved = backup(db, backup_dir, label)
    receipt_path = saved.with_suffix(".receipt.json")
    receipt = dict(schema=SCHEMA, command=label, status="PENDING", database=str(_db(db)),
                   source=source, target=target, backup=str(saved), backup_sha256=sha(saved.read_bytes()),
                   plan=before, fixture_moves=[])
    receipt["fixture_moves"] = [[str(a), str(b)] for a, b in moves]
    receipt["recovery"] = ("Stop services. Check database and every fixture source/destination; "
                           "restore the backup via SQLite with services stopped, and restore fixture "
                           "paths from fixture_moves without overwriting. Keep this receipt for audit.")
    _write_receipt(receipt_path, receipt, create=True)
    connection = None
    moved = []
    committed = False
    try:
        connection = sqlite3.connect(str(_db(db)), isolation_level=None, timeout=1)
        connection.execute("BEGIN EXCLUSIVE")
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
        require(fixture_dirs(fixture_root, connection, source, moved=(label == "rollback")) == paths,
                "fixture set changed since plan")
        for path, destination in moves:
            require(path.is_dir() and not destination.exists(), "fixture paths changed since plan")
            path.rename(destination)
            moved.append((path, destination))
        connection.execute("COMMIT")
        committed = True
    except BaseException as error:
        recovery_errors = []
        if connection is not None and connection.in_transaction:
            try:
                connection.execute("ROLLBACK")
            except Exception as rollback_error:
                recovery_errors.append(str(rollback_error))
        for path, destination in reversed(moved):
            try:
                require(not path.exists() and destination.is_dir(), "fixture rollback paths changed")
                destination.rename(path)
            except Exception as rollback_error:
                recovery_errors.append(str(rollback_error))
        raise MigrationError("migration failed; inspect PENDING receipt %s (committed=%s; recovery errors=%s): %s"
                             % (receipt_path, committed, recovery_errors, error)) from error
    finally:
        if connection is not None:
            connection.close()
    receipt.update(status="PASS", verify=check, fixtures_moved=[[str(a), str(b)] for a, b in moved])
    # Write a new file and replace the pending receipt atomically: any failure leaves
    # the original PENDING recovery instructions intact.
    final_path = receipt_path.with_suffix(".complete.tmp")
    try:
        _write_receipt(final_path, receipt, create=True)
        os.replace(final_path, receipt_path)
    except OSError as error:
        raise MigrationError("database committed; inspect PENDING receipt %s: %s" % (receipt_path, error)) from error
    return dict(receipt, receipt=str(receipt_path))


def verify_connection(connection, expected):
    """Check this migrator's preconditions and markers, not live-store health."""
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
                                if _replace(json.loads(r[0]), expected, expected, table)[1])
    return dict(expected=expected, scope="migration-preconditions-and-markers-not-store-health",
                markers=[m["table"] for m in markers], rows_naming_expected=counts)


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
