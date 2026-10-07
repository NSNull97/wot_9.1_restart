"""Build bounded, data-only P02 hangar state from a server-owned test_lab snapshot.

This owns no credentials or account registry. With --profile, the domain ID is
the shared web users.id; without it, the old disposable diagnostic fixture remains.
Client-derived descriptors are read only from local evidence and never checked in.
The pickle writer emits only primitive values: no object, import, reduce or memo
opcodes. Nothing received from a client is deserialized here.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import pickletools
import re
import struct
import uuid

from client_audit import ROOT, config, output_dir, read_limited, save_json, sha256
from packed_xml import decode as decode_packed_xml, walk as walk_packed_xml


MAX_BYTES = 16384
MAX_NODES = 4096
MAX_DEPTH = 16
FIXTURE_VERSION = 1


def encode_data(value) -> bytes:
    """Encode a restricted primitive tree as Python 2 compatible protocol 2.

    str means UTF-8 Python 2 str, not unicode. Keys are restricted to bytes/str/int.
    Tuples are distinct from lists. No user methods or constructors are called.
    """
    output = bytearray(b'\x80\x02')
    remaining = MAX_NODES
    active = set()

    def emit(data):
        if len(output) + len(data) > MAX_BYTES:
            raise ValueError('pickle output exceeds 16 KiB')
        output.extend(data)

    def visit(item, depth):
        nonlocal remaining
        remaining -= 1
        if remaining < 0 or depth > MAX_DEPTH:
            raise ValueError('pickle tree exceeds node/depth bound')
        kind = type(item)
        if item is None:
            emit(b'N')
        elif kind is bool:
            emit(b'\x88' if item else b'\x89')
        elif kind is int:
            if not -(1 << 31) <= item < (1 << 31):
                raise ValueError('only signed 32-bit fixture integers supported')
            if 0 <= item <= 255:
                emit(b'K' + bytes([item]))
            elif 0 <= item <= 65535:
                emit(b'M' + struct.pack('<H', item))
            else:
                emit(b'J' + struct.pack('<i', item))
        elif kind is float:
            if not math.isfinite(item):
                raise ValueError('non-finite fixture number')
            emit(b'G' + struct.pack('>d', item))
        elif kind in (str, bytes):
            data = item.encode('utf-8') if kind is str else item
            if len(data) > MAX_BYTES:
                raise ValueError('fixture string exceeds bound')
            emit((b'U' + bytes([len(data)]) if len(data) < 256
                  else b'T' + struct.pack('<I', len(data))) + data)
        elif kind in (dict, list, tuple):
            identity = id(item)
            if identity in active:
                raise ValueError('cyclic fixture tree')
            active.add(identity)
            if len(item) > MAX_NODES:
                raise ValueError('fixture collection exceeds bound')
            if kind is tuple:
                if not item:
                    emit(b')')
                else:
                    emit(b'(')
                    for child in item:
                        visit(child, depth + 1)
                    emit(b't')
            elif kind is list:
                emit(b']')
                if item:
                    emit(b'(')
                    for child in item:
                        visit(child, depth + 1)
                    emit(b'e')
            else:
                emit(b'}')
                if item:
                    emit(b'(')
                    keys = set()
                    for key, child in item.items():
                        if type(key) not in (str, bytes, int):
                            raise ValueError('fixture keys must be string or integer')
                        wire_key = key.encode('utf-8') if type(key) is str else key
                        if wire_key in keys:
                            raise ValueError('fixture keys collide after Python 2 encoding')
                        keys.add(wire_key)
                        visit(key, depth + 1)
                        visit(child, depth + 1)
                    emit(b'u')
            active.remove(identity)
        else:
            raise ValueError('fixture type is not a primitive')

    visit(value, 0)
    emit(b'.')
    return bytes(output)


def bounded_hex(value, name, maximum):
    if type(value) is not str or len(value) > maximum * 2 or len(value) % 2:
        raise ValueError(name + ': invalid bounded hex')
    try:
        raw = bytes.fromhex(value)
    except ValueError as error:
        raise ValueError(name + ': invalid hex') from error
    if raw.hex() != value.lower():
        raise ValueError(name + ': noncanonical hex')
    return raw


def bounded_int(value, name, low, high):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(name + ': out of range')
    return value


def resource_reference_price(native_name, type_compact_descr, client_root):
    """Read a display reference from this original client's bounded vehicle list.

    This adds no purchase service. The original ItemsRequester enumerates even
    inventory vehicles through itemPrices, so an owned reference must be present.
    _xml.readPrice returns (0, amount) when price/gold exists, else (amount, 0).
    """
    if not re.fullmatch(r'[a-z_]{1,24}:[A-Za-z0-9_-]{1,64}', native_name):
        raise ValueError('vehicle resource name outside bounded path syntax')
    nation, vehicle_name = native_name.split(':', 1)
    path = client_root / 'res/scripts/item_defs/vehicles' / nation / 'list.xml'
    data = read_limited(path, 2 * 1024 * 1024)
    prefix = '/' + vehicle_name + '[1]'
    values = dict(walk_packed_xml(decode_packed_xml(data)))
    if values.get(prefix + '/id[1]') != type_compact_descr >> 8:
        raise ValueError('vehicle list and native descriptor type IDs disagree')
    price_path = prefix + '/price[1]'
    price = bounded_int(values.get(price_path), 'client reference price', 0, (1 << 31) - 1)
    is_gold = price_path + '/gold[1]' in values
    return ((0, price) if is_gold else (price, 0)), {
        'file': str(path), 'sha256': hashlib.sha256(data).hexdigest(),
        'node': price_path, 'source_value': price, 'gold_child_present': is_gold,
        'classification': 'VERIFIED_RESOURCE; display reference only, trades unavailable',
    }


def mounted_module_reference_prices(native, client_root):
    """Read only the five mounted MS-1 UI references from original #717 XML.

    The observed uncustomized one-turret descriptor has a two-byte header,
    <4H chassis/engine/fuelTank/radio, <2H turret/gun, then zero flags.
    Original VehicleDescr.__initFromCompactDescr line1325 and
    _splitVehicleCompactDescr line6093 establish this ordering. Numeric IDs
    and prices are read from configured local resources, never copied into
    this source as a substitute catalogue. No trade capability is granted.
    """
    if native.get('type_name') != 'ussr:MS-1':
        raise ValueError('mounted catalogue v2 supports only the verified MS-1')
    compact = bounded_hex(native.get('compact_descr_hex'), 'mounted vehicle descriptor', 15)
    if len(compact) != 15 or compact[0] != 1 or compact[14] != 0:
        raise ValueError('mounted catalogue requires measured uncustomized descriptor layout')
    if native.get('type_compact_descr') != (compact[1] << 8) | compact[0]:
        raise ValueError('mounted vehicle type and descriptor disagree')
    components = native.get('components')
    keys = {'chassis', 'engine', 'fuelTank', 'radio', 'turret', 'gun'}
    if type(components) is not dict or set(components) != keys:
        raise ValueError('mounted component names differ from measured descriptor')
    ids = dict(zip(('chassis', 'engine', 'fuelTank', 'radio', 'turret', 'gun'),
                   struct.unpack('<6H', compact[2:14])))
    type_ids = {'chassis': 2, 'turret': 3, 'gun': 4, 'engine': 5, 'fuelTank': 6, 'radio': 7}
    for kind in keys:
        cd = bounded_int(components[kind], 'mounted component ID', 1, 0xFFFFFF)
        if cd != (ids[kind] << 8) | type_ids[kind]:
            raise ValueError('mounted component ID differs from original descriptor bytes')
    base = client_root.resolve() / 'res/scripts/item_defs/vehicles/ussr'
    cache = {}

    def resource(relative):
        if relative not in cache:
            path = (base / relative).resolve(strict=True)
            if not path.is_relative_to(client_root.resolve()):
                raise ValueError('component resource escaped original client')
            raw = read_limited(path, 2 * 1024 * 1024)
            cache[relative] = (dict(walk_packed_xml(decode_packed_xml(raw))),
                               {'file': str(path), 'sha256': hashlib.sha256(raw).hexdigest()})
        return cache[relative]

    files = {'chassis': 'chassis', 'turret': 'turrets', 'gun': 'guns',
             'engine': 'engines', 'radio': 'radios'}
    names, id_sources = {}, {}
    for kind, filename in files.items():
        values, source = resource('components/' + filename + '.xml')
        matches = [(node, value) for node, value in values.items()
                   if re.fullmatch(r'/ids\[1\]/[A-Za-z0-9_.-]{1,96}\[1\]', node)
                   and type(value) is int and value == ids[kind]]
        if len(matches) != 1:
            raise ValueError('mounted component XML ID is absent or ambiguous')
        node, value = matches[0]
        names[kind] = node[len('/ids[1]/'):-3]
        id_sources[kind] = dict(source, node=node, source_value=value)
    vehicle_values, vehicle_source = resource('ms-1.xml')
    local_nodes = {
        'chassis': '/chassis[1]/' + names['chassis'] + '[1]',
        'turret': '/turrets0[1]/' + names['turret'] + '[1]',
        'gun': '/turrets0[1]/' + names['turret'] + '[1]/guns[1]/' + names['gun'] + '[1]',
        'engine': '/engines[1]/' + names['engine'] + '[1]',
        'radio': '/radios[1]/' + names['radio'] + '[1]',
    }
    prices, sources = {}, []
    for kind in ('chassis', 'turret', 'gun', 'engine', 'radio'):
        node = local_nodes[kind]
        values, source = vehicle_values, vehicle_source
        if node not in values:
            raise ValueError('mounted component is not in original MS-1 definition')
        if node + '/price[1]' not in values:
            if values[node] != 'shared':
                raise ValueError('unmeasured component price inheritance')
            values, source = resource('components/' + files[kind] + '.xml')
            node = '/shared[1]/' + names[kind] + '[1]'
        price_node = node + '/price[1]'
        amount = bounded_int(values.get(price_node), 'mounted reference price', 0, (1 << 31) - 1)
        gold = price_node + '/gold[1]' in values
        price = (0, amount) if gold else (amount, 0)
        prices[components[kind]] = price
        sources.append({'component': kind, 'compact_descr': components[kind],
                        'id_source': id_sources[kind],
                        'price_source': dict(source, node=price_node, source_value=amount,
                                             gold_child_present=gold),
                        'classification': 'VERIFIED_RESOURCE; mounted display reference; trades unavailable'})
    return prices, sources


def descriptors(path: Path | None, catalog_version=1):
    bounded_int(catalog_version, 'compatibility catalogue revision', 1, 2)
    if path is None:
        return None, None
    _, paths = config()
    path = path.resolve(strict=True)
    if not path.is_relative_to(paths['local_artifacts_root']):
        raise ValueError('native descriptors must remain in local evidence')
    raw = read_limited(path, 65536)
    value = json.loads(raw.decode('utf-8'))
    if type(value) is not dict or type(value.get('vehicle')) is not dict:
        raise ValueError('expected native descriptor object with vehicle')
    vehicle = value['vehicle']
    compact = bounded_hex(vehicle['compact_descr_hex'], 'vehicle descriptor', 1024)
    if not 15 <= len(compact) <= 1024:
        raise ValueError('vehicle descriptor length')
    compact_id = bounded_int(vehicle['type_compact_descr'], 'vehicle type ID', 1, 0xFFFFFF)
    if compact_id & 15 != 1 or compact_id & 0xFF != compact[0] or compact_id >> 8 != compact[1]:
        raise ValueError('vehicle integer/byte descriptor IDs disagree')
    name = vehicle['type_name']
    if type(name) is not str or not 1 <= len(name) <= 80 or ':' not in name:
        raise ValueError('native vehicle name absent')
    hp = bounded_int(vehicle['max_health'], 'vehicle max health', 1, 10000)
    roles = vehicle['crew_roles']
    if type(roles) is not list or not 1 <= len(roles) <= 8:
        raise ValueError('native crew roles absent')
    for role_set in roles:
        if (type(role_set) is not list or not 1 <= len(role_set) <= 8
                or any(type(role) is not str or not 1 <= len(role) <= 32 for role in role_set)):
            raise ValueError('native crew role shape invalid')
    account_dossier = bounded_hex(value['account_dossier_hex'], 'account dossier', 4096)
    if not account_dossier:
        raise ValueError('native new-account dossier descriptor absent')
    components_raw = vehicle.get('components', {})
    if type(components_raw) is not dict or len(components_raw) > 8:
        raise ValueError('native component list invalid')
    components = {}
    for key, component in components_raw.items():
        if type(key) is not str:
            raise ValueError('native component name invalid')
        if type(component) is dict:
            component = component['compact_descr']
        components[key] = bounded_int(component, 'native component ID', 1, 0xFFFFFF)
    price, price_source = resource_reference_price(name, compact_id, paths['original_client_root'])
    normalized = {'type_name': name, 'type_compact_descr': compact_id,
                  'compact_descr_hex': compact.hex(), 'max_health': hp,
                  'crew_roles': roles, 'components': components,
                  'account_dossier_hex': account_dossier.hex(), 'reference_price': price}
    source = {'file': str(path), 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest(),
              'reference_price_source': price_source}
    if catalog_version == 2:
        prices, provenance = mounted_module_reference_prices(normalized, paths['original_client_root'])
        normalized['mounted_module_prices'] = prices
        source['mounted_module_price_sources'] = provenance
    return normalized, source


def read_profile(path):
    """Read a server-owned snapshot; never credentials or arbitrary client data."""
    if path is None:
        return None, None
    _, paths = config()
    source = Path(path).resolve(strict=True)
    if not source.is_relative_to(paths['local_artifacts_root']):
        raise ValueError('profile snapshot must remain in local')
    raw = read_limited(source, 8192)
    value = json.loads(raw.decode('utf-8'))
    expected = {'profile_version', 'account_id', 'username', 'native_database_id',
                'created_at_ms', 'snapshot_revision', 'resources', 'statistics'}
    if type(value) is not dict or set(value) != expected or value['profile_version'] != 1:
        raise ValueError('unsupported game profile schema')
    if type(value['account_id']) is not str or str(uuid.UUID(value['account_id'])) != value['account_id']:
        raise ValueError('canonical account UUID required')
    # profile v1's historical field name is retained. Its value is the immutable
    # displayed nickname, never the email login or a new credential registry.
    if (type(value['username']) is not str
            or not re.fullmatch(r'[A-Za-zА-Яа-яЁё0-9_]{3,24}', value['username'])
            or len(value['username'].encode('utf-8')) > 48):
        raise ValueError('stored NFC Russian/Latin display nickname required')
    bounded_int(value['native_database_id'], 'native account ID', 1, (1 << 31) - 1)
    bounded_int(value['created_at_ms'], 'registration timestamp', 1, 4000000000000)
    bounded_int(value['snapshot_revision'], 'snapshot revision', 1, 1)
    if type(value['resources']) is not dict or set(value['resources']) != {'credits', 'gold', 'free_xp'}:
        raise ValueError('resource schema')
    for resource in value['resources'].values():
        bounded_int(resource, 'resource balance', 0, (1 << 31) - 1)
    if (type(value['statistics']) is not dict
            or value['statistics'] != {'battles': 0, 'wins': 0, 'losses': 0, 'draws': 0}
            or any(type(x) is not int for x in value['statistics'].values())):
        raise ValueError('v1 accepts only a real new-account zero-battle profile')
    return value, {'file': str(source), 'sha256': hashlib.sha256(raw).hexdigest()}


def registered_account_dossier(original, created_at_ms):
    """Set only creationTime in the verified #717 fresh account dossier layout.

    Native DossierBuilder uses <H + 34*H (70 B). Account layout index11 is
    total; records are creationTime:I,lastBattleTime:I,battleLifeTime:I,
    treesCut:H,mileage:I (18 B). All other fresh blocks have size0.
    Strict template validation prevents accidental editing of a played dossier.
    """
    if len(original) != 88:
        raise ValueError('unrecognized fresh account dossier length')
    header = struct.unpack_from('<35H', original)
    sizes = header[1:]
    if header[0] != 80 or sizes[11] != 18 or sum(sizes) != 18 or any(original[74:]):
        raise ValueError('not the verified empty #717 account dossier')
    created_seconds = bounded_int(created_at_ms // 1000, 'dossier registration seconds', 1, 4000000000)
    return original[:70] + struct.pack('<I', created_seconds) + original[74:]


def fixture(native=None, profile=None, catalog_version=1):
    """Own domain state and its narrow #717 mapping; no account writes or trades."""
    bounded_int(catalog_version, 'compatibility catalogue revision', 1, 2)
    if catalog_version == 2 and native is None:
        raise ValueError('catalogue v2 requires actual native mounted descriptors')
    model = {
        'fixture_version': FIXTURE_VERSION, 'ruleset': 'test_lab',
        'account_id': 'test_lab:hangar-player-v1', 'display_name': 'p02-hangar-player',
        'resources': {'credits': 100000, 'gold': 0, 'free_xp': 0},
        'statistics': {'battles': 0, 'wins': 0, 'losses': 0, 'draws': 0},
        'clan': None,
        'play_time_policy': {'name': 'unrestricted_test_lab',
                             'daily_limit_seconds': 86400,
                             'weekly_limit_seconds': 604800},
        'statistics_provenance': 'New account; original native fresh dossier descriptor; no battles invented',
        'capacity': {'vehicle_slots': 3, 'crew_berths': 16},
        'capacity_price_policy': {
            'name': 'unavailable_test_lab_reference',
            'slot_base_capacity': 3, 'slot_reference_prices': [0],
            'berth_base_capacity': 16, 'berth_pack_size': 1,
            'berth_reference_prices': [0],
            'provenance': 'Own display references; capacity purchases unavailable; not historical prices',
        },
        'inventory': [],
        'capabilities': {'purchases': False, 'sales': False, 'battle': False,
                         'crew_recruitment': False, 'persistence': False},
        'identity_integration': 'NOT_RUN; diagnostic fixture is not an account registry',
        'resource_provenance': 'Owner-selected test_lab balance, not historical initial balance',
    }
    stats = {'credits': 100000, 'gold': 0, 'freeXP': 0, 'slots': 3, 'berths': 16,
             # ProfileUtils.getProfileCommonInfo line 336 uses `is not None`
             # before indexing clanInfo[1]; [] is not the no-clan sentinel.
             'dossier': b'', 'clanInfo': None, 'accOnline': 0, 'accOffline': 0,
             'freeTMenLeft': 0, 'freeVehiclesLeft': [], 'vehicleSellsLeft': 0,
             'captchaTriesLeft': 0, 'hasFinPassword': False, 'finPswdAttemptsLeft': 0,
             'tkillIsSuspected': False, 'denunciationsLeft': 0,
             'tutorialsCompleted': 0, 'battlesTillCaptcha': 0,
             # Original GameSessionController.isParentControlEnabled line 202:
             # enabled iff day < 86400 or week < 604800. Zero means blocked.
             'dailyPlayHours': [0] * 31, 'playLimits': ((86400, ''), (604800, '')),
             'globalRating': 0, 'vehTypeXP': {}, 'vehTypeLocks': {},
             'restrictions': {}, 'globalVehicleLocks': {},
             'unlocks': [], 'eliteVehicles': [], 'multipliedXPVehs': []}
    state = {'rev': 1, 'inventory': {1: {'compDescr': {}}, 8: {'compDescr': {}}},
             'stats': stats,
             'account': {'clanDBID': 0, 'attrs': 0, 'premiumExpiryTime': 0, 'autoBanTime': 0},
             'cache': {'isFinPswdVerified': False, 'mayConsumeWalletResources': True,
                       'unitAcceptDeadline': 0},
             'economics': {'unlocks': [], 'eliteVehicles': []},
             # ServerSettingsManager.__version == 11, original class line 33.
             'quests': {}, 'tokens': {}, 'intUserSettings': {0: 11}}
    # A revisioned, read-only catalog; add only the owned native reference below.
    # Exchange/trade commands remain unavailable at the gateway, not fake success.
    shop = {'rev': 1, 'sellPriceFactor': 0.0, 'dailyXPFactor': 1,
            # Original Shop.getNextSlotPrice line 362 expects TWO fields;
            # getNextBerthPackPrice line 388 expects THREE (including pack size).
            # These are own read-only references, not a free purchase service.
            'slotsPrices': (3, [0]), 'berthsPrices': (16, 1, [0]),
            'items': {'itemPrices': {}, 'notInShopItems': [], 'vehiclesToSellForGold': []},
            'premiumCost': {}, 'tankmanCost': [], 'dropSkillsCost': {},
            'camouflageCost': {}, 'playerInscriptionCost': {}, 'playerEmblemCost': {},
            'isEnabledBuyingGoldShellsForCredits': False,
            'isEnabledBuyingGoldEqsForCredits': False}
    compatibility = {'client_build': 'v.0.9.1 #717', 'native_database_id': 900001,
                     'client_name': model['display_name'], 'vehicle_mapping': [],
                     'compatibility_catalog_revision': catalog_version}
    if profile:
        model.update({'account_id': profile['account_id'], 'display_name': profile['username'],
                      'created_at_ms': profile['created_at_ms'],
                      'snapshot_revision': profile['snapshot_revision'],
                      'identity_integration': 'Shared users.id; credentials verified only by web identity store'})
        model['resources'] = dict(profile['resources'])
        stats.update({'credits': profile['resources']['credits'], 'gold': profile['resources']['gold'],
                      'freeXP': profile['resources']['free_xp']})
        model['capabilities']['persistence'] = True
        compatibility.update({'native_database_id': profile['native_database_id'],
                              'account_id': profile['account_id'],
                              'client_name': profile['username']})
    if native:
        inventory_id = 1
        cd = native['type_compact_descr']
        state['inventory'][1].update({
            'compDescr': {inventory_id: bytes.fromhex(native['compact_descr_hex'])},
            'repair': {inventory_id: (0, native['max_health'])},
            'crew': {inventory_id: [None] * len(native['crew_roles'])},
            'settings': {inventory_id: 0}, 'shells': {inventory_id: []},
            'shellsLayout': {inventory_id: {}},
            'eqs': {inventory_id: [0, 0, 0]}, 'eqsLayout': {inventory_id: [0, 0, 0]},
        })
        stats['dossier'] = bytes.fromhex(native['account_dossier_hex'])
        if profile:
            stats['dossier'] = registered_account_dossier(stats['dossier'], profile['created_at_ms'])
            model['statistics_provenance'] = 'Original fresh #717 layout, creationTime from users.created_at; zero played battles'
        stats['vehTypeXP'] = {cd: 0}
        stats['unlocks'] = [cd] + sorted(set(native['components'].values()))
        shop['items']['itemPrices'][cd] = native['reference_price']
        shop['items']['notInShopItems'] = [cd]
        if catalog_version == 2:
            prices = native.get('mounted_module_prices')
            expected = {native['components'][key] for key in ('chassis', 'turret', 'gun', 'engine', 'radio')}
            if type(prices) is not dict or len(prices) != 5 or set(prices) != expected:
                raise ValueError('catalogue v2 requires exactly five verified mounted prices')
            for price in prices.values():
                if type(price) is not tuple or len(price) != 2:
                    raise ValueError('mounted reference price pair required')
                for amount in price:
                    bounded_int(amount, 'mounted reference amount', 0, (1 << 31) - 1)
            shop['rev'] = 2
            shop['items']['itemPrices'].update(prices)
            # Current fitted modules remain enumerable by VEHICLE.SUITABLE.
            # Hidden/reference status alone is not an economic permission gate.
            shop['items']['notInShopItems'].extend(sorted(prices))
        model['inventory'] = [{'inventory_id': (profile['account_id'] + ':starter-vehicle-v1') if profile else 'test_lab:starter-vehicle-v1',
                               'research_name': native['type_name'], 'crew_assigned': False,
                               'ammunition_count': 0, 'state': 'owned; battle unavailable'}]
        compatibility['vehicle_mapping'].append({
            'inventory_id': model['inventory'][0]['inventory_id'],
            'native_inventory_id': inventory_id, 'type_compact_descr': cd,
            'descriptor_source': 'native original VehicleDescr constructor; local evidence'})
    return model, compatibility, {'state.bin': state, 'shop.bin': shop, 'dossier.bin': (0, [])}


def json_tree(value):
    """Review representation; preserves bytes, tuple and integer-key distinctions."""
    if type(value) is bytes:
        return {'bytes_hex': value.hex()}
    if type(value) is tuple:
        return {'tuple': [json_tree(item) for item in value]}
    if type(value) is dict:
        return {'pairs': [[json_tree(key), json_tree(item)] for key, item in value.items()]}
    if type(value) is list:
        return [json_tree(item) for item in value]
    return value


def self_test():
    checks = []
    vectors = [(None, b'\x80\x02N.'), (0, b'\x80\x02K\x00.'),
               (-1, b'\x80\x02J\xff\xff\xff\xff.'),
               (256, b'\x80\x02M\x00\x01.'), (65536, b'\x80\x02J\x00\x00\x01\x00.'),
               (b'\xff', b'\x80\x02U\x01\xff.'),
               ((0, []), b'\x80\x02(K\x00]t.'),
               ({'rev': 1}, b'\x80\x02}(U\x03revK\x01u.')]
    for i, (value, expected) in enumerate(vectors):
        if encode_data(value) != expected:
            raise AssertionError('exact pickle vector ' + str(i))
        checks.append({'check': 'exact_vector_' + str(i), 'status': 'PASS'})
    cyclic = []
    cyclic.append(cyclic)
    deep = []
    for _ in range(MAX_DEPTH + 2):
        deep = [deep]
    invalid = [('cycle', cyclic), ('depth', deep), ('nodes', [None] * MAX_NODES),
               ('bytes', b'x' * MAX_BYTES), ('int64', 1 << 31),
               ('nan', float('nan')), ('object', object()), ('set', {1}),
               ('unsupported_key', {(1, 2): 0}), ('colliding_keys', {'x': 1, b'x': 2})]
    for name, value in invalid:
        try:
            encode_data(value)
        except ValueError:
            checks.append({'check': 'reject_' + name, 'status': 'PASS'})
        else:
            raise AssertionError('accepted invalid ' + name)
    # pickletools reads instructions without object construction or execution.
    for name, value in fixture()[2].items():
        ops = [op.name for op, _, _ in pickletools.genops(encode_data(value))]
        if {'GLOBAL', 'REDUCE', 'BUILD', 'OBJ', 'INST', 'NEWOBJ', 'PERSID', 'BINPERSID'} & set(ops):
            raise AssertionError('unsafe opcode')
        checks.append({'check': 'data_only_' + name, 'status': 'PASS', 'opcodes': sorted(set(ops))})
    return {'status': 'PASS', 'checks': checks,
            'scope': 'Encoder boundaries and exact bytes only; native compatibility NOT_RUN here'}


def run(args):
    native, source = descriptors(Path(args.native_descriptors) if args.native_descriptors else None,
                                 catalog_version=args.catalog_version)
    profile, profile_source = read_profile(args.profile)
    if profile and native is None:
        raise ValueError('registered account requires native descriptors')
    model, compatibility, trees = fixture(native, profile, catalog_version=args.catalog_version)
    payloads = {name: encode_data(tree) for name, tree in trees.items()}
    out = output_dir(args.out)
    if profile_source and Path(profile_source['file']).parent == out:
        # The bridge atomically publishes this directory by renaming it. Keep
        # provenance resolvable after publication without changing old evidence.
        profile_source = dict(profile_source,
                              file=Path(profile_source['file']).name,
                              relative_to='fixture_directory')
    names = list(payloads) + ['fixture.json', 'compatibility.json', 'payloads.json',
                              'manifest.json', 'encoder-tests.json']
    if any((out / name).exists() for name in names):
        raise FileExistsError('append-only evidence: use a fresh output directory')
    for name, raw in payloads.items():
        with (out / name).open('xb') as stream:
            stream.write(raw)
    save_json(out / 'fixture.json', model)
    save_json(out / 'compatibility.json', compatibility)
    save_json(out / 'payloads.json', {name: json_tree(tree) for name, tree in trees.items()})
    checks = self_test()
    save_json(out / 'encoder-tests.json', checks)
    report = {'fixture_version': FIXTURE_VERSION, 'ruleset': 'test_lab',
              'compatibility_catalog_revision': args.catalog_version,
              'native_compatibility': 'NOT_RUN; acceptance requires real server/client exchange',
              'native_descriptors': source,
              'profile_source': profile_source,
              'vehicle_available': native is not None,
              'account_id': model['account_id'], 'native_database_id': compatibility['native_database_id'],
              'play_time_policy': model['play_time_policy'],
              'capacity_price_policy': model['capacity_price_policy'],
              'statistics': model['statistics'],
              'clan': model['clan'],
              'statistics_provenance': model['statistics_provenance'],
              'generator': {'file': str(Path(__file__).resolve()), 'sha256': sha256(Path(__file__))},
              'files': [{'file': name, 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest(),
                         'opcodes': sorted(set(op.name for op, _, _ in pickletools.genops(raw)))}
                        for name, raw in payloads.items()]}
    save_json(out / 'manifest.json', report)
    print(json.dumps({'output': str(out), 'payloads': report['files'],
                      'encoder_checks': len(checks['checks']), 'native_vehicle': native is not None}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True, help='Fresh local evidence directory')
    parser.add_argument('--native-descriptors', help='Native read-only descriptor evidence JSON')
    parser.add_argument('--profile', help='Server-owned version1 profile snapshot in local; never credentials')
    parser.add_argument('--catalog-version', type=int, choices=(1, 2), default=2,
                        help='Native display catalogue revision, independent of account snapshot (default: 2)')
    run(parser.parse_args())
