"""Bounded data-only native #717 projection for the opt-in P09D service.

This module never unpickles. The imported JSON primitive tree must re-encode to
the exact hash-bound profile4 payloads before it can be a projection source.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import struct

from content_bundle import Bundle
from profile4_chain import verify_profile4_chain
from p09c_ammo_catalog import MOUNTS, SHELLS, CATALOG_SHA256

MAX_BYTES = 16384
MAX_NODES = 4096
MAX_DEPTH = 16
MAX_UPDATE = 240  # Fits the measured outgoing VAR1 native method envelope.
SHOP_REVISION = 3  # Exact accepted profile4 shop.bin, distinct from Account rev1.


def encode(value, maximum=MAX_BYTES):
    """Protocol2 primitives only; no constructors, reducers, memo or imports."""
    out, active = bytearray(b'\x80\x02'), set()
    nodes = 0
    def emit(raw):
        if len(out) + len(raw) > maximum:
            raise ValueError('native projection byte bound')
        out.extend(raw)
    def visit(item, depth):
        nonlocal nodes
        nodes += 1
        if nodes > MAX_NODES or depth > MAX_DEPTH:
            raise ValueError('native projection node/depth bound')
        kind = type(item)
        if item is None: emit(b'N')
        elif kind is bool: emit(b'\x88' if item else b'\x89')
        elif kind is int:
            if not -(1 << 31) <= item < (1 << 31): raise ValueError('native integer bound')
            emit(b'K' + bytes([item]) if 0 <= item <= 255 else b'M' + struct.pack('<H', item)
                 if 0 <= item <= 65535 else b'J' + struct.pack('<i', item))
        elif kind is float:
            if not math.isfinite(item): raise ValueError('nonfinite primitive')
            emit(b'G' + struct.pack('>d', item))
        elif kind in (bytes, str):
            raw = item.encode('utf-8') if kind is str else item
            emit((b'U' + bytes([len(raw)]) if len(raw) < 256 else b'T' + struct.pack('<I', len(raw))) + raw)
        elif kind in (dict, list, tuple):
            if id(item) in active or len(item) > MAX_NODES: raise ValueError('cyclic/large primitive')
            active.add(id(item))
            if kind is dict:
                emit(b'}')
                if item:
                    emit(b'('); seen = set()
                    for key, child in item.items():
                        if type(key) not in (int, str, bytes, tuple): raise ValueError('primitive key')
                        if type(key) is tuple and (len(key) != 2 or any(type(v) is not int for v in key)):
                            raise ValueError('bounded mounted tuple key')
                        wire = key.encode('utf-8') if type(key) is str else key
                        if wire in seen: raise ValueError('duplicate wire key')
                        seen.add(wire); visit(key, depth + 1); visit(child, depth + 1)
                    emit(b'u')
            elif kind is list:
                emit(b']')
                if item:
                    emit(b'(')
                    for child in item: visit(child, depth + 1)
                    emit(b'e')
            elif item:
                emit(b'(')
                for child in item: visit(child, depth + 1)
                emit(b't')
            else: emit(b')')
            active.remove(id(item))
        else: raise ValueError('nonprimitive output')
    visit(value, 0); emit(b'.')
    return bytes(out)


def tree(value):
    """Decode the existing authored JSON descriptor, never executable pickle."""
    count = 0
    def visit(item, depth):
        nonlocal count
        count += 1
        if count > MAX_NODES or depth > MAX_DEPTH: raise ValueError('descriptor bounds')
        if type(item) is dict:
            if set(item) == {'bytes_hex'}:
                text = item['bytes_hex']
                if type(text) is not str or len(text) > 2 * MAX_BYTES: raise ValueError('hex bound')
                raw = bytes.fromhex(text)
                if raw.hex() != text: raise ValueError('noncanonical hex')
                return raw
            if set(item) == {'tuple'} and type(item['tuple']) is list:
                return tuple(visit(v, depth + 1) for v in item['tuple'])
            if set(item) == {'pairs'} and type(item['pairs']) is list:
                result = {}
                for pair in item['pairs']:
                    if type(pair) is not list or len(pair) != 2: raise ValueError('descriptor pair')
                    key, val = (visit(v, depth + 1) for v in pair)
                    if type(key) not in (str, bytes, int, tuple) or key in result: raise ValueError('descriptor key')
                    result[key] = val
                return result
            raise ValueError('descriptor tag')
        if type(item) is list: return [visit(v, depth + 1) for v in item]
        if item is None or type(item) in (int, float, str, bool): return item
        raise ValueError('descriptor primitive')
    return visit(value, 0)


class ProjectionSource:
    def __init__(self, bundle_root):
        self.proof = verify_profile4_chain(bundle_root)
        self.bundle = Bundle(bundle_root)
        self.profile_bytes = self.bundle.read('fixtures/profile4/profile-input.json')
        self.profile = self.bundle.read_json('fixtures/profile4/profile-input.json')
        self.compatibility = self.bundle.read_json('fixtures/profile4/compatibility.json')
        self.fixture = self.bundle.read_json('fixtures/profile4/fixture.json')
        descriptors = self.bundle.read_json('fixtures/profile4/payloads.json')
        self.trees, self.raw = {}, {}
        for name in ('state.bin', 'shop.bin', 'dossier.bin'):
            value = tree(descriptors[name]); raw = self.bundle.read('fixtures/profile4/' + name)
            if encode(value) != raw: raise ValueError('bundle descriptor/payload differs')
            self.trees[name], self.raw[name] = value, raw
        self.bundle_sha256 = hashlib.sha256((Path(bundle_root) / 'manifest.json').read_bytes()).hexdigest()
        if self.trees['state.bin']['rev'] != 1: raise ValueError('base wire revision')
        if self.trees['shop.bin']['rev'] != SHOP_REVISION: raise ValueError('base shop revision')
        if self.trees['state.bin']['inventory'][1]['shells'][1] != [2570, 20, 2826, 0, 3082, 0]:
            raise ValueError('base ammo projection')

    def state(self, aggregate, layouts):
        state = deepcopy(self.trees['state.bin'])
        state['rev'] = 1  # Connection-local AccountSyncData sequence resets at login.
        inventory = state['inventory']
        inventory[10] = {SHELLS[k].native_compact_id: v for k, v in aggregate['depot'].items()}
        for native_id, layout in layouts.items():
            mount = MOUNTS['ms1-stock' if native_id == 1 else 'is7-stock']
            flat = [value if index % 2 else abs(value) for index, value in enumerate(layout)]
            inventory[1]['shells'][native_id] = flat
            inventory[1]['shellsLayout'][native_id] = {
                (mount.turret_native_compact_id, mount.gun_native_compact_id): list(layout)}
        return state

    def fixture_files(self, profile, aggregate, layouts):
        state = encode(self.state(aggregate, layouts))
        compat = deepcopy(self.compatibility)
        compat.update(snapshot_revision=aggregate['revision'])
        compat['ammo_mapping'] = [dict(shell_definition_id=shell_id,
            native_shell_compact_descr=SHELLS[shell_id].native_compact_id,
            vehicle_inventory_id=item['vehicle_id'], native_vehicle_inventory_id=1 if item['mount_id'] == 'ms1-stock' else 2,
            native_turret_compact_descr=MOUNTS[item['mount_id']].turret_native_compact_id,
            native_gun_compact_descr=MOUNTS[item['mount_id']].gun_native_compact_id)
            for item in aggregate['ammunition'] for shell_id in MOUNTS[item['mount_id']].shell_ids]
        info = dict(version=1, account_id=profile['account_id'], native_database_id=profile['native_database_id'],
                    revision=aggregate['revision'], wire_revision=1, catalog_sha256=CATALOG_SHA256,
                    state_sha256=hashlib.sha256(state).hexdigest(), purchases=False, battle=False)
        dossier = compat['dossier_cache']
        manifest = dict(fixture_version=5, profile_version=5, snapshot_revision=aggregate['revision'],
                        wire_sync_revision=1, compatibility_catalog_revision=3, ruleset='test_lab',
                        account_id=profile['account_id'], native_database_id=profile['native_database_id'],
                        grant=profile['test_grant'], preservation={'dossier_cache': {
                            **dossier, 'payload_sha256': hashlib.sha256(self.raw['dossier.bin']).hexdigest()}},
                        source_bundle_sha256=self.bundle_sha256,
                        profile_sha256=hashlib.sha256(canonical(profile)).hexdigest())
        return {'state.bin': state, 'shop.bin': self.raw['shop.bin'], 'dossier.bin': self.raw['dossier.bin'],
                'manifest.json': canonical(manifest), 'compatibility.json': canonical(compat),
                'ammo-service.json': canonical(info), 'profile-input.json': canonical(profile)}


def canonical(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('ascii')


def update_delta(native_id, layout, depot, wire_revision):
    mount = MOUNTS['ms1-stock' if native_id == 1 else 'is7-stock']
    if type(wire_revision) is not int or not 1 <= wire_revision < 2**31 - 1: raise ValueError('wire revision')
    positive = [value if index % 2 else abs(value) for index, value in enumerate(layout)]
    value = {'prevRev': wire_revision, 'rev': wire_revision + 1,
             'inventory': {1: {'shells': {native_id: positive}, 'shellsLayout': {native_id: {
                 (mount.turret_native_compact_id, mount.gun_native_compact_id): list(layout)}}},
                           10: {SHELLS[key].native_compact_id: depot[key] for key in mount.shell_ids}}}
    return encode(value, MAX_UPDATE)
