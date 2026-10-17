"""Explicit readonly Selection5 CLI precursor; never native Ready/admission."""
from contextlib import closing, contextmanager
from pathlib import Path
import argparse
import json
import sqlite3
import stat
import sys

DENIALS = frozenset(('INVALID_INPUT', 'STALE_REVISION', 'SOURCE_STAMP_MISMATCH',
    'NATIVE_STATE_STAMP_MISMATCH', 'RUN_NOT_OPEN', 'RUN_FENCED', 'VEHICLE_RESERVED',
    'UNKNOWN_VEHICLE', 'BATTLE_PROFILE_UNSUPPORTED', 'OWNER_ACCEPTANCE_REQUIRED',
    'INCOMPLETE_CREW', 'AMMUNITION_EMPTY', 'AMMUNITION_UNSUPPORTED',
    'AMMO_LOSS_POLICY_REQUIRED', 'OWNER_HOLD_POLICY_REQUIRED',
    'OWNER_CONTRACT_UNSUPPORTED'))


def repository_root(script):
    # Production imports follow this script, never cwd or a request/env root.
    for root in tuple(script.resolve(strict=True).parents)[:10]:
        if ((root / 'server/gateway/Cargo.toml').is_file()
                and (root / 'tools/p08b_battle_service.py').is_file()):
            return root
    raise RuntimeError('selection_hold_repository_root_unavailable')


def bootstrap():
    script = Path(__file__).resolve(strict=True)
    root = repository_root(script)
    for directory in (root, root / 'tools', script.parent):
        name = str(directory)
        if name in sys.path:
            sys.path.remove(name)
        sys.path.insert(0, name)


def plain_database(value):
    """An existing configured file, not a URI or an implicit new SQLite DB."""
    p = Path(value)
    if not p.is_absolute() or '..' in p.parts or str(p).startswith(('\\\\', '//')):
        raise ValueError('configured_database_path')
    for q in (p, *p.parents):
        info = q.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
            raise ValueError('configured_database_link')
    if not p.is_file():
        raise ValueError('configured_database_file')
    return p.resolve(strict=True)


@contextmanager
def configured_store(database, catalog, account_id, shell_catalog, terminal_policy):
    """Real constructor with a preflight and an explicit query-only boundary.

    The inherited constructor requires an existing file. Its reviewed current
    implementation only connects/sets PRAGMAs and builds verified fields; it
    does not initialize/migrate schemas. Its handle IS briefly RW-capable.
    Never describe this as mode=ro from the first constructor connection.
    Allocation is split only to close a connection if genuine __init__ fails;
    no fields/init steps are fabricated, copied, skipped or monkeypatched.
    """
    from p08b_owner_hold_store import OwnerHoldStore, namespace, hold_owner
    from p09d_ammo_store import require

    path = plain_database(database)
    with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=2)) as proof:
        proof.execute('PRAGMA query_only=ON')
        proof.execute('BEGIN')
        try:
            require(namespace(proof) and hold_owner(proof, account_id), 'OWNER_HOLD_POLICY_REQUIRED')
            require(proof.execute('SELECT catalog_sha256 FROM battle_owner_hold_schema').fetchone()[0]
                    == catalog.sha256, 'UNSUPPORTED_OWNER_HOLD_SCHEMA')
        finally:
            proof.rollback()

    require(OwnerHoldStore.__new__ is object.__new__, 'SELECTION_CONFIG_REQUIRED')
    store = OwnerHoldStore.__new__(OwnerHoldStore)
    try:
        OwnerHoldStore.__init__(store, path, catalog, account_id=account_id,
                               shell_catalog=shell_catalog, terminal_policy=terminal_policy)
        connection = store.connection
        require(not connection.in_transaction and connection.total_changes == 0, 'SELECTION_CONFIG_REQUIRED')
        connection.execute('PRAGMA query_only=ON')
        require(connection.execute('PRAGMA query_only').fetchone()[0] == 1, 'SELECTION_CONFIG_REQUIRED')
        require(store.hold_active(), 'OWNER_HOLD_POLICY_REQUIRED')
        yield store
    finally:
        # A failing genuine constructor may already have opened this handle.
        connection = getattr(store, 'connection', None)
        if connection is not None:
            connection.close()


def main():
    from game_profile_tx import TransactionError
    from p09e_research_catalog import load_catalog
    from p08b_owner_source import projection_source
    from p10b_selection_hold import SelectionHoldReader, parse_request, MAX_REQUEST, MAX_REPLY
    from p09d_ammo_projection import canonical

    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('database', 'bundle', 'original-root', 'account-id', 'shell-catalog', 'terminal-policy'):
        parser.add_argument('--' + name, required=True)
    args = parser.parse_args()
    raw = sys.stdin.buffer.read(MAX_REQUEST + 1)
    try:
        request = parse_request(raw, args.account_id)
    except (ValueError, UnicodeError, RecursionError) as error:
        raise TransactionError('INVALID_INPUT') from error
    # Catalog and source paths are operator-configured argv, never stdin fields.
    catalog = load_catalog(args.original_root)
    with configured_store(args.database, catalog, args.account_id,
                          args.shell_catalog, args.terminal_policy) as store:
        source = projection_source(args.bundle, catalog, args.database, args.account_id)
        reply = SelectionHoldReader(store, source).select(request, authenticated_account_id=args.account_id)
        output = canonical(reply)
        if len(output) > MAX_REPLY:
            raise TransactionError('SELECTION_REPLY_BOUND')
    sys.stdout.buffer.write(output)


def entry():
    try:
        bootstrap()
        from game_profile_tx import TransactionError
        try:
            main()
        except TransactionError as error:
            if error.code not in DENIALS:
                raise
            output = json.dumps(dict(error='selection_not_ready', code=error.code),
                                sort_keys=True, separators=(',', ':')).encode('ascii')
            sys.stdout.buffer.write(output)
    except Exception:
        print('selection_hold_worker_invalid_or_unavailable', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(entry())
