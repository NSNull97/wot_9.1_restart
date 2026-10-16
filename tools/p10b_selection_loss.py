"""Additive API4 training selection for the explicit native room service route.

This reader owns only a bounded query-only snapshot and source projection.
No selection reply can be produced from a bare no-reservation Inspect.
"""
from contextlib import contextmanager
from copy import deepcopy
import re
from game_profile_tx import TransactionError
from p08b_battle_projection import BattleProjectionSource
from p04m_pool_projection import PoolProjectionSource
from p06t_ammo_loss_store import AmmoLossStore, AmmoLossProjectionSource, CONTRACT, POLICY_SHA256 as LOSS_POLICY_SHA256
from p06t_mixed_store import POLICY_SHA256, SOURCE_SHA256
from p06t_terminal import MANIFEST_SHA256
from p08b_battle_store import _uuid, _integer
from p09d_ammo_store import require, sha
from p09d_ammo_projection import canonical
from destructible_catalog import json_value

SCHEMA = 'p10b-owned-selection-loss.v1'
MAX_REQUEST, MAX_REPLY = 3072, 6144
STAMP_KEYS = {'native_state_sha256','owner_source_sha256','catalog_sha256','pool_registry_sha256',
              'mixed_policy_sha256','shell_catalog_sha256','terminal_policy_sha256',
              'loss_policy_sha256','loss_companion_sha256'}
REQUEST_KEYS = {'version','contract','operation','account_id','native_database_id','run_id',
                'expected_revision','native_inventory_id','projection_stamp'}


def validate_request(value, authenticated_account_id):
    require(type(value) is dict and set(value) == REQUEST_KEYS, 'INVALID_INPUT')
    require(type(value['version']) is int and value['version'] == 4
            and value['contract'] == CONTRACT and value['operation'] == 'select', 'INVALID_INPUT')
    require(value['account_id'] == authenticated_account_id, 'FOREIGN_ACCOUNT')
    _uuid(authenticated_account_id); _uuid(value['run_id'])
    _integer(value['native_database_id'],1,2**31-1)
    _integer(value['native_inventory_id'],1,2**31-1)
    _integer(value['expected_revision'],13,2**31-1)
    stamp = value['projection_stamp']
    require(type(stamp) is dict and set(stamp) == STAMP_KEYS
            and all(type(s) is str and re.fullmatch('[0-9a-f]{64}',s) for s in stamp.values()), 'INVALID_INPUT')
    require(stamp['loss_policy_sha256'] == LOSS_POLICY_SHA256, 'AMMO_LOSS_POLICY_REQUIRED')
    require(len(canonical(value)) <= MAX_REQUEST, 'INVALID_INPUT')
    return deepcopy(value)


def parse_request(raw, authenticated_account_id):
    return validate_request(json_value(raw,limit=MAX_REQUEST,nodes=64,depth=3),authenticated_account_id)


def fingerprint(binding):
    return sha(canonical(binding))


@contextmanager
def read_snapshot(connection):
    """Snapshot ownership is explicit; caller's ambient transaction is refused."""
    require(not connection.in_transaction, 'SELECTION_TRANSACTION_REQUIRED')
    previous = connection.execute('PRAGMA query_only').fetchone()[0]
    connection.execute('PRAGMA query_only=ON')
    try:
        connection.execute('BEGIN')
        yield connection
    finally:
        connection.rollback()
        connection.execute('PRAGMA query_only=' + ('ON' if previous else 'OFF'))


class SelectionLossReader:
    def __init__(self, store, source):
        require(type(store) is AmmoLossStore and isinstance(source,BattleProjectionSource), 'SELECTION_CONFIG_REQUIRED')
        require(source.catalog.sha256 == store.catalog.sha256, 'SOURCE_STAMP_MISMATCH')
        self.store, self.source = store, source

    def select(self, request, *, authenticated_account_id):
        request = validate_request(request, authenticated_account_id)
        store, source = self.store, self.source
        require(request['account_id'] == store.pool_account == source.profile['account_id']
                and request['native_database_id'] == source.profile['native_database_id'], 'FOREIGN_ACCOUNT')
        with read_snapshot(store.connection) as c:
            # This first query fixes the WAL snapshot before every authority read.
            if c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='p06v3_owner'").fetchone():
                require(c.execute('SELECT 1 FROM p06v3_owner WHERE account_id=?',(store.pool_account,)).fetchone() is None,
                        'OWNER_CONTRACT_UNSUPPORTED')
            require(store.pool_active() and store.mixed_active() and store.loss_active(), 'AMMO_LOSS_POLICY_REQUIRED')
            imported = c.execute('SELECT base_json,base_sha256,bundle_sha256 FROM p09d_import WHERE account_id=?',
                                 (store.pool_account,)).fetchone()
            require(imported is not None and sha(imported[0].encode('ascii')) == imported[1]
                    and type(source.profile_bytes) is bytes and source.profile_bytes == imported[0].encode('ascii')
                    and imported[2] == source.bundle_sha256, 'SOURCE_STAMP_MISMATCH')
            snapshot = store.read_profile(store.pool_account)
            public = store._project_profile(store.pool_account,snapshot)
            require(public['native_database_id'] == request['native_database_id'], 'FOREIGN_ACCOUNT')
            current = store._current_run(store.pool_account)
            require(current is not None, 'RUN_NOT_OPEN'); require(current == request['run_id'], 'RUN_FENCED')
            require(snapshot['revision'] == request['expected_revision'], 'STALE_REVISION')
            # _active_mixed includes API4's shared base reservations. Any API2
            # active row also refuses READY; no active contract may be hidden.
            require(not store._active_mixed(store.pool_account) and c.execute(
                "SELECT 1 FROM p08b_reservation WHERE account_id=? AND status='active'",(store.pool_account,)).fetchone() is None
                and all(r['state']=='available' and r['battle_id'] is None for r in snapshot['vehicles']), 'VEHICLE_RESERVED')
            frozen_base = store.freeze_mixed(snapshot,request['native_inventory_id'])
            # Use the real pure wrapper factory; this object is not a reservation.
            frozen = store._wrapper({'frozen':frozen_base,'frozen_sha256':sha(canonical(frozen_base))})
            projection = AmmoLossProjectionSource(PoolProjectionSource(source,store),store)
            files = projection.fixture_files(public,snapshot,store.layouts(store.pool_account))
            stamp = dict(owner_source_sha256=source.bundle_sha256,catalog_sha256=store.catalog.sha256,
                pool_registry_sha256=store.registry.sha256,mixed_policy_sha256=POLICY_SHA256,
                shell_catalog_sha256=SOURCE_SHA256,terminal_policy_sha256=MANIFEST_SHA256,
                native_state_sha256=sha(files['state.bin']),loss_policy_sha256=LOSS_POLICY_SHA256,
                loss_companion_sha256=sha(files['p06t-ammo-loss.json']))
            require(request['projection_stamp'] == stamp, 'SOURCE_STAMP_MISMATCH')
            binding = dict(schema=SCHEMA,contract=CONTRACT,account_id=store.pool_account,
                native_database_id=request['native_database_id'],run_id=current,native_inventory_id=request['native_inventory_id'],
                revision=snapshot['revision'],projection_stamp=stamp,aggregate_sha256=sha(canonical(snapshot)),
                frozen_sha256=sha(canonical(frozen)))
            reply = dict(version=4,operation='select',status='ready',**binding,frozen=frozen,fingerprint=fingerprint(binding))
            require(len(canonical(reply)) <= MAX_REPLY, 'SELECTION_TOO_LARGE')
            return reply
