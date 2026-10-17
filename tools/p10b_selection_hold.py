"""Additive read-only Selection5 precursor. Never a reservation or native Ready.

Only an explicitly configured exact OwnerHoldStore and trusted owner source may
produce this typed source proof. API2/4 readers and training mode fences remain
unchanged. Source/bootstrap paths are never accepted in the request.
"""
from copy import deepcopy
import re

from p08b_battle_projection import BattleProjectionSource
from p04m_pool_projection import PoolProjectionSource
from p08b_owner_hold_store import OwnerHoldStore, OwnerHoldProjectionSource, CONTRACT, POLICY_SHA256 as HOLD_POLICY_SHA256
from p06t_ammo_loss_store import POLICY_SHA256 as LOSS_POLICY_SHA256
from p06t_mixed_store import POLICY_SHA256 as MIXED_POLICY_SHA256, SOURCE_SHA256
from p06t_terminal import MANIFEST_SHA256
from p08b_battle_store import _uuid, _integer
from p09d_ammo_store import require, sha
from p09d_ammo_projection import canonical
from destructible_catalog import json_value
from p10b_selection_loss import read_snapshot

VERSION = 5
SCHEMA = 'p10b-owned-selection-hold.v1'
MAX_REQUEST, MAX_REPLY = 4096, 12288
STAMP_KEYS = {'native_state_sha256', 'owner_source_sha256', 'catalog_sha256',
              'pool_registry_sha256', 'mixed_policy_sha256', 'shell_catalog_sha256',
              'terminal_policy_sha256', 'loss_policy_sha256', 'loss_companion_sha256',
              'hold_policy_sha256', 'hold_companion_sha256'}
REQUEST_KEYS = {'version', 'contract', 'operation', 'account_id', 'native_database_id',
                'run_id', 'native_inventory_id', 'expected_revision', 'projection_stamp'}
REPLY_KEYS = {'version', 'contract', 'operation', 'status', 'schema', 'account_id',
              'native_database_id', 'run_id', 'native_inventory_id', 'revision',
              'projection_stamp', 'aggregate_sha256', 'frozen_sha256', 'frozen', 'fingerprint'}


def validate_request(value, authenticated_account_id):
    require(type(value) is dict and set(value) == REQUEST_KEYS, 'INVALID_INPUT')
    require(type(value['version']) is int and value['version'] == VERSION
            and value['contract'] == CONTRACT and value['operation'] == 'select', 'INVALID_INPUT')
    require(type(value['account_id']) is str and value['account_id'] == authenticated_account_id, 'FOREIGN_ACCOUNT')
    _uuid(authenticated_account_id); _uuid(value['run_id'])
    _integer(value['native_database_id'], 1, 2**31-1)
    _integer(value['native_inventory_id'], 1, 2**31-1)
    _integer(value['expected_revision'], 13, 2**31-1)
    stamp = value['projection_stamp']
    require(type(stamp) is dict and set(stamp) == STAMP_KEYS
            and all(type(v) is str and re.fullmatch('[0-9a-f]{64}', v) for v in stamp.values()), 'INVALID_INPUT')
    require(stamp['hold_policy_sha256'] == HOLD_POLICY_SHA256, 'OWNER_HOLD_POLICY_REQUIRED')
    require(stamp['loss_policy_sha256'] == LOSS_POLICY_SHA256, 'AMMO_LOSS_POLICY_REQUIRED')
    require(len(canonical(value)) <= MAX_REQUEST, 'INVALID_INPUT')
    return deepcopy(value)


def parse_request(raw, authenticated_account_id):
    return validate_request(json_value(raw, limit=MAX_REQUEST, nodes=80, depth=3), authenticated_account_id)


def fingerprint(binding):
    """Digest recipe only; this function does not confer source authority."""
    return sha(canonical(binding))


class SelectionHoldReader:
    """Short read-only transaction over the configured5 authority.

    Initialization/activation/run_open/admit/publication are outside this reader.
    Reject any active contract for this owner. A no-reservation Inspect is not a
    proof of selected crew, ammunition, mounts or current projected source.
    """
    def __init__(self, store, source):
        require(type(store) is OwnerHoldStore and isinstance(source, BattleProjectionSource), 'SELECTION_CONFIG_REQUIRED')
        require(source.catalog.sha256 == store.catalog.sha256, 'SOURCE_STAMP_MISMATCH')
        self.store, self.source = store, source

    def select(self, request, *, authenticated_account_id):
        request = validate_request(request, authenticated_account_id)
        store, source = self.store, self.source
        require(request['account_id'] == store.pool_account == source.profile['account_id']
                and request['native_database_id'] == source.profile['native_database_id'], 'FOREIGN_ACCOUNT')
        with read_snapshot(store.connection) as c:
            # First authority SELECT fixes the WAL snapshot. Every subsequent
            # schema/owner/profile/run/vehicle/layout/projector query uses it.
            if c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='p06v3_owner'").fetchone():
                require(c.execute('SELECT 1 FROM p06v3_owner WHERE account_id=?', (store.pool_account,)).fetchone() is None,
                        'OWNER_CONTRACT_UNSUPPORTED')
            require(store.pool_active() and store.mixed_active() and store.loss_active() and store.hold_active(),
                    'OWNER_HOLD_POLICY_REQUIRED')
            imported = c.execute('SELECT base_json,base_sha256,bundle_sha256 FROM p09d_import WHERE account_id=?',
                                 (store.pool_account,)).fetchone()
            # The genuine AnchorA import is ASCII raw source, not necessarily
            # canonical JSON. Reordering equal input must not acquire authority.
            require(imported is not None and type(imported[0]) is str
                    and sha(imported[0].encode('ascii')) == imported[1]
                    and type(source.profile_bytes) is bytes and source.profile_bytes == imported[0].encode('ascii')
                    and imported[2] == source.bundle_sha256, 'SOURCE_STAMP_MISMATCH')
            aggregate = store.read_profile(store.pool_account)
            public = store._project_profile(store.pool_account, aggregate)
            require(public['native_database_id'] == request['native_database_id'], 'FOREIGN_ACCOUNT')
            current = store._current_run(store.pool_account)
            require(current is not None, 'RUN_NOT_OPEN')
            require(current == request['run_id'], 'RUN_FENCED')
            require(aggregate['revision'] == request['expected_revision'], 'STALE_REVISION')
            # Active5 uses the shared base mixed row. Include old AP base and
            # every owned vehicle, never just the selected available row.
            require(not store._active_mixed(store.pool_account) and c.execute(
                "SELECT 1 FROM p08b_reservation WHERE account_id=? AND status='active'", (store.pool_account,)).fetchone() is None
                and all(v['state'] == 'available' and v['battle_id'] is None for v in aggregate['vehicles']), 'VEHICLE_RESERVED')
            base = store.freeze_mixed(aggregate, request['native_inventory_id'])
            loss = store._wrapper({'frozen':base, 'frozen_sha256':sha(canonical(base))})
            frozen = store._hold_wrapper(loss)
            projection = OwnerHoldProjectionSource(PoolProjectionSource(source, store), store)
            layouts = store.layouts(store.pool_account)
            files = projection.fixture_files(public, aggregate, layouts)
            companion = json_value(files['p08b-owner-hold.json'], limit=4096, nodes=128, depth=5)
            selected = [row for row in companion['native_layouts'] if row['native_inventory_id'] == request['native_inventory_id']]
            profile = store.registry.profiles[base['kind']]
            mount = store.mounts[profile.assembly_id]
            require(len(selected) == 1 and selected[0]['shells_layout'] == layouts[request['native_inventory_id']]
                    and selected[0]['turret_compact_id'] == mount.turret_native_compact_id
                    and selected[0]['gun_compact_id'] == mount.gun_native_compact_id, 'SOURCE_STAMP_MISMATCH')
            stamp = dict(native_state_sha256=sha(files['state.bin']), owner_source_sha256=source.bundle_sha256,
                catalog_sha256=store.catalog.sha256, pool_registry_sha256=store.registry.sha256,
                mixed_policy_sha256=MIXED_POLICY_SHA256, shell_catalog_sha256=SOURCE_SHA256,
                terminal_policy_sha256=MANIFEST_SHA256, loss_policy_sha256=LOSS_POLICY_SHA256,
                loss_companion_sha256=sha(files['p06t-ammo-loss.json']), hold_policy_sha256=HOLD_POLICY_SHA256,
                hold_companion_sha256=sha(files['p08b-owner-hold.json']))
            require(request['projection_stamp'] == stamp, 'SOURCE_STAMP_MISMATCH')
            binding = dict(schema=SCHEMA, contract=CONTRACT, account_id=store.pool_account,
                native_database_id=request['native_database_id'], run_id=current,
                native_inventory_id=request['native_inventory_id'], revision=aggregate['revision'],
                projection_stamp=stamp, aggregate_sha256=sha(canonical(aggregate)), frozen_sha256=sha(canonical(frozen)))
            reply = dict(version=VERSION, operation='select', status='ready', **binding,
                         frozen=frozen, fingerprint=fingerprint(binding))
            require(set(reply) == REPLY_KEYS and len(canonical(reply)) <= MAX_REPLY, 'SELECTION_TOO_LARGE')
            return reply
