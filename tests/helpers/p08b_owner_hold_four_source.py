"""Closed disposable TEST import of four preexisting owners; no game authority.

Public build_fixture() accepts no source/destination/config override. It copies
two exact preserved DBs into a fresh C-temp run, never activates a game mode or
calls a game writer. The private SQL functions exist for transactional tests.
"""
from contextlib import ExitStack, closing
from pathlib import Path
import hashlib
import json
import re
import sqlite3
import tempfile
import uuid

ROOT = Path(__file__).resolve().parents[2]
from p08b_owner_hold_four_context import original_root
SCHEMA_SHA = "51768438aaa436c968bdda9f4e2171c75623b5e1c0a2b9217f5f37267c7e3ad7"
SOURCES = (
    ("local/evidence/20261016-p06t-owned01/seed01/seed.json",
     "56ecea1b3548a13efbac9d3870ee27fa96dc639557b124bd608a0abbcffe0e4b",
     "f4c7f9174b208e9c42d6668cf7796a9026693c1ebea87bbd0eeeadd581f2debf",
     {"c5326cc1-8524-479c-8bba-72e973489c22": 1,
      "271022a3-41e0-406e-b6fa-59930c320442": 2}),
    ("local/night-staging/20261016/p10b-selection-http01/seed01/seed.json",
     "50d4c10623d94b63a50621650429b34beffdbc48dee2176028e2f62b07da3287",
     "a04216d90e8e9e8b379fc2d34a0fed9f400e373d8d4c591d723bb00a1accc2cf",
     {"80ad3bc2-476e-4fbd-899d-a4679ea167d2": 3,
      "633ad84f-f33f-4aab-bacd-421f31a93bae": 4}),
)
ACCOUNT_TABLES = (
    "game_profiles", "game_snapshot", "game_vehicle", "game_command_ledger",
    "p04d_crew_member", "p04d_crew_meta", "p04f_crew_meta", "p04g_crew_meta",
    "p04h_crew_meta", "p04i_crew_meta", "p04j_crew_meta", "p04j_retired_member",
    "p04k_crew_meta", "p04m_owner", "p06t_command", "p06t_owner",
    "p06t_reservation", "p06t_result", "p08b_reservation", "p08b_run",
    "p09c_ammo_depot", "p09c_ammo_mount", "p09d_import",
    "p09d_native_command", "p09d_native_layout", "p09e_research",
)
GLOBAL_TABLES = (
    "game_limits", "game_meta", "p04d_schema", "p04f_schema", "p04g_schema",
    "p04h_schema", "p04i_schema", "p04j_schema", "p04k_schema", "p04m_schema",
    "p06t_schema", "p08b_schema", "p09c_schema", "p09d_schema", "p09e_schema",
    "sqlite_sequence",
)
ALL_TABLES = ACCOUNT_TABLES + GLOBAL_TABLES
MAX_DB_BYTES = 16 * 1024 * 1024
DESCRIPTOR_SHA = "18e6c2babfc205ce80fa24c2c9f23385a1731233c4d504be369638485652d6f2"


def require(ok, message):
    if not ok:
        raise ValueError(message)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")


def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for part in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(part)
    return h.hexdigest()


def plain(value, existing=True):
    path = Path(value)
    require(path.is_absolute() and ".." not in path.parts, "absolute lexical path required")
    for part in (path, *path.parents):
        require(not (part.exists() and (part.is_symlink() or part.is_junction())), "links refused")
    return path.resolve(strict=existing)


def _check_pin(path, expected):
    require(path.is_file() and 0 < path.stat().st_size <= MAX_DB_BYTES,
            "bounded existing source required")
    require(sha(path) == expected, "source SHA mismatch")


def _source(index):
    metadata, metadata_sha, db_sha, accounts = SOURCES[index]
    meta_path = plain(original_root(ROOT) / metadata)
    require(meta_path.stat().st_size <= 65536, "source metadata bound")
    _check_pin(meta_path, metadata_sha)
    seed = json.loads(meta_path.read_bytes())
    source = plain(seed["database"])
    require(source == meta_path.with_name("game.sqlite"), "closed sibling source required")
    _check_pin(source, db_sha)
    require(seed.get("database_sha256") in (None, db_sha), "metadata DB binding mismatch")
    require({row["account_id"] for row in seed["profiles"]} == set(accounts), "metadata owner set")
    # A stale 32-KiB SHM is not a committed-data journal. Immutable SQLite
    # never reads/writes it; nonempty WAL/journal still refuses. Sources have
    # exact raw DB pins, not a caller-supplied checkpoint/normalization recipe.
    for suffix in ("-wal", "-journal"):
        side = Path(str(source) + suffix)
        require(not side.exists() or side.stat().st_size == 0, "source sidecar refused")
    return source, meta_path


def _ro(path):
    db = sqlite3.connect(path.as_uri() + "?mode=ro&immutable=1", uri=True)
    db.execute("PRAGMA query_only=ON")
    db.execute("BEGIN")
    return db


def _schema(db):
    rows = db.execute("SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name").fetchall()
    require(len(rows) == 97, "unsupported schema object count")
    result = {}
    for kind, name, table, sql in rows:
        require(kind in ("table", "index", "trigger"), "unsupported schema object")
        tokens = re.findall(r"'(?:''|[^'])*'|\"(?:\"\"|[^\"])*\"|\w+|[^\s]", sql or "")
        result[name] = {"kind": kind, "table": table,
                        "tokens": [v if v[:1] in ('"', "'") else v.lower() for v in tokens]}
    require(hashlib.sha256(canonical(result)).hexdigest() == SCHEMA_SHA, "unsupported exact schema")
    require({r[1] for r in rows if r[0] == "table"} == set(ALL_TABLES), "closed table set")
    require(db.execute("PRAGMA user_version").fetchone()[0] == 1, "user_version mismatch")
    return result


def _columns(db, table):
    require(table in ALL_TABLES, "closed table required")
    columns = tuple(row[1] for row in db.execute('PRAGMA table_info("' + table + '")'))
    require(columns and all(re.fullmatch(r"[a-z_][a-z0-9_]*", c) for c in columns), "column bound")
    require(("account_id" in columns) == (table in ACCOUNT_TABLES), "scoping column mismatch")
    return columns


def _cell(value):
    if value is None:
        return ["null"]
    if isinstance(value, bytes):
        return ["blob", value.hex()]
    require(type(value) in (str, int, float), "unsupported SQL scalar")
    return [type(value).__name__, value]


def _row_key(row):
    value = canonical([_cell(v) for v in row])
    require(len(value) <= 2 * 1024 * 1024, "SQL cell byte bound")
    return value


def _rows(db, table):
    require(table in ALL_TABLES, "closed table required")
    rows = []
    size = 0
    for row in db.execute('SELECT * FROM "' + table + '"'):
        size += len(_row_key(row))
        require(len(rows) < 10000 and size <= 16 * 1024 * 1024, "SQL table bound")
        rows.append(tuple(row))
    return sorted(rows, key=_row_key)


def _fingerprint(rows):
    return {"rows": len(rows), "sha256": hashlib.sha256(
        canonical([hashlib.sha256(_row_key(r)).hexdigest() for r in rows])).hexdigest()}


def _lineage(db, owners):
    found = dict(db.execute("SELECT account_id,native_id FROM game_profiles"))
    require(found == owners, "exact owner/native set required")
    result = {}
    for account, native in sorted(owners.items()):
        public_raw = db.execute("SELECT profile_json FROM game_profiles WHERE account_id=?", (account,)).fetchone()[0]
        revision, snap_raw, snap_sha = db.execute("SELECT revision,snapshot_json,snapshot_sha256 FROM game_snapshot WHERE account_id=?", (account,)).fetchone()
        base_raw, base_sha, bundle_sha, grant_raw, grant_sha = db.execute(
            "SELECT base_json,base_sha256,bundle_sha256,grant_json,grant_sha256 FROM p09d_import WHERE account_id=?", (account,)).fetchone()
        research_raw, research_sha = db.execute("SELECT state_json,state_sha256 FROM p09e_research WHERE account_id=?", (account,)).fetchone()
        for raw, expected in ((snap_raw, snap_sha), (base_raw, base_sha), (grant_raw, grant_sha), (research_raw, research_sha)):
            require(len(raw) <= 1024 * 1024 and hashlib.sha256(raw.encode("ascii")).hexdigest() == expected,
                    "raw lineage SHA mismatch")
        public, imported, snapshot = (json.loads(raw) for raw in (public_raw, base_raw, snap_raw))
        require(public["account_id"] == imported["account_id"] == account
                and public["native_database_id"] == imported["native_database_id"] == native,
                "source identity binding mismatch")
        require(public["profile_version"] == 13 and public["snapshot_revision"] == revision
                and snapshot["revision"] == revision and snapshot["account_id"] == account,
                "current profile/snapshot revision mismatch")
        vehicles = list(db.execute("SELECT state,battle_id FROM game_vehicle WHERE account_id=?", (account,)))
        require(vehicles and all(state == "available" and battle is None for state, battle in vehicles), "source vehicle reserved")
        result[account] = {"native_database_id": native, "revision": revision,
                           "raw_import_sha256": base_sha, "source_bundle_sha256": bundle_sha,
                           "snapshot_sha256": snap_sha,
                           "public_sha256": hashlib.sha256(public_raw.encode("ascii")).hexdigest(),
                           "grant_sha256": grant_sha}
    return result


def _snapshot(db, owners):
    schema = _schema(db)
    require(db.execute("PRAGMA integrity_check").fetchall() == [("ok",)], "source integrity failure")
    require(not db.execute("PRAGMA foreign_key_check").fetchall(), "source foreign key failure")
    columns = {t: _columns(db, t) for t in ALL_TABLES}
    rows = {t: _rows(db, t) for t in ALL_TABLES}
    for table in ACCOUNT_TABLES:
        pos = columns[table].index("account_id")
        require(all(row[pos] in owners for row in rows[table]), "foreign owner rows refused")
    for table in ("p06t_reservation", "p08b_reservation"):
        require(not db.execute('SELECT 1 FROM "' + table + '" WHERE status=\'active\' LIMIT 1').fetchone(), "active reserve refused")
    return {"schema": schema, "columns": columns, "rows": rows, "owners": _lineage(db, owners)}


def _validate_pair(a, b):
    require(a["schema"] == b["schema"] and a["columns"] == b["columns"], "schema mismatch")
    require(not set(a["owners"]) & set(b["owners"]), "account collision")
    require(not {v["native_database_id"] for v in a["owners"].values()}
            & {v["native_database_id"] for v in b["owners"].values()}, "native collision")
    for table in GLOBAL_TABLES:
        if table not in ("game_meta", "game_limits", "sqlite_sequence"):
            require(a["rows"][table] == b["rows"][table], "global policy/catalog mismatch")
    require(a["rows"]["game_meta"] == [("native_descriptors_sha256", DESCRIPTOR_SHA)]
            and b["rows"]["game_meta"] == [], "exact descriptor baseline mismatch")
    require(a["rows"]["sqlite_sequence"] == [("game_profiles", 2)]
            and b["rows"]["sqlite_sequence"] == [("game_profiles", 4)], "source sequence mismatch")


def _merge(destination, a, b):
    require(not destination.in_transaction, "ambient transaction refused")
    require(destination.execute("PRAGMA foreign_keys").fetchone()[0] == 1, "foreign_keys must be enabled")
    _validate_pair(a, b)
    destination.execute("BEGIN IMMEDIATE")
    try:
        current = _snapshot(destination, SOURCES[0][3])
        require(current == a, "target changed since source backup")
        destination.execute("PRAGMA defer_foreign_keys=ON")
        for table in ACCOUNT_TABLES:
            columns = b["columns"][table]
            query = 'INSERT INTO "' + table + '" (' + ",".join('"' + c + '"' for c in columns) + ") VALUES (" + ",".join("?" for _ in columns) + ")"
            if b["rows"][table]:
                destination.executemany(query, b["rows"][table])
        all_owners = {**SOURCES[0][3], **SOURCES[1][3]}
        actual = _snapshot(destination, all_owners)
        for table in ACCOUNT_TABLES:
            require(actual["rows"][table] == sorted(a["rows"][table] + b["rows"][table], key=_row_key), "scoped row changed")
        for table in GLOBAL_TABLES:
            expected = [("game_profiles", 4)] if table == "sqlite_sequence" else a["rows"][table]
            require(actual["rows"][table] == expected, "retained A global changed")
        require(actual["owners"] == {**a["owners"], **b["owners"]}, "owner lineage changed")
        destination.commit()
        return actual
    except BaseException:
        destination.rollback()
        raise


def _allocate():
    temporary = plain(Path(tempfile.gettempdir()))
    require(temporary.drive.lower() == "c:", "C-temp output required")
    base = temporary / "WoT-p08b-hold-four-owner-v1"
    if not base.exists():
        base.mkdir()
    base = plain(base)
    run = base / ("run-" + uuid.uuid4().hex)
    run.mkdir()
    plain(run)
    database = run / "game.sqlite"
    with database.open("xb"):
        pass
    return database


def _save(path, value):
    with path.open("xb") as stream:
        stream.write(canonical(value) + b"\n")


def build_fixture():
    """No caller-defined source, target, SQL, identity or gameplay policy."""
    sources = [_source(i) for i in range(2)]
    target = _allocate()
    try:
        with ExitStack() as stack:
            dbs = [stack.enter_context(closing(_ro(path))) for path, _ in sources]
            snapshots = [_snapshot(db, SOURCES[i][3]) for i, db in enumerate(dbs)]
            _validate_pair(*snapshots)
            out = stack.enter_context(closing(sqlite3.connect(target)))
            dbs[0].backup(out)
            out.execute("PRAGMA foreign_keys=ON")
            actual = _merge(out, *snapshots)
            for db in dbs:
                db.rollback()
        for i, (path, meta) in enumerate(sources):
            _source(i)
        receipt = {"schema": "p08b-owner-hold-four-owner-test-import.v1",
            "status": "PASS_EXACT_SQL_TEST_FIXTURE_ONLY", "database": str(target),
            "database_sha256": sha(target), "source_db_pins": [s[2] for s in SOURCES],
            "schema_sha256": SCHEMA_SHA, "owners": actual["owners"],
            "tables": {t: _fingerprint(actual["rows"][t]) for t in ALL_TABLES},
            "source_unchanged": True, "all_original_rows_exact": True,
            "global_baseline": "A", "game_limits": "A_UNCHANGED",
            "native_descriptors_sha256": DESCRIPTOR_SHA, "natural_native_sequence": 4,
            "new_game_accounts": 0, "new_grants": 0, "game_mode_activation": "NOT_PERFORMED",
            "native_runtime_http_world": "NOT_RUN", "existing_onboard_api_changed": False}
        _save(target.with_name("receipt.json"), receipt)
        return receipt
    except BaseException as exc:
        _save(target.with_name("failure.json"), {"schema": "p08b-owner-hold-four-owner-test-import-failure.v1",
              "status": "FAILED_RETAINED", "type": type(exc).__name__, "message": str(exc),
              "target": str(target), "target_sha256": sha(target)})
        raise


if __name__ == "__main__":
    import sys
    require(len(sys.argv) == 1, "no source/destination override supported")
    result = build_fixture()
    print(canonical({"status": result["status"], "database": result["database"],
                     "owners": len(result["owners"]), "receipt_sha256": sha(Path(result["database"]).with_name("receipt.json"))}).decode("ascii"))
