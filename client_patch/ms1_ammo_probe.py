# -*- coding: utf-8 -*-
"""Opt-in, read-only original #717 MS-1 ammunition export/observation.

No descriptor replacement, inventory mutation, RPC, selection or UI action.
Native compatibility is established by a real run, never by the pure tests.
The caller must already have a connected, synced Hangar. Inventory MS-1 is
read even when another owned vehicle is selected; selection remains untouched.
"""
import hashlib
import json
import os
import traceback

try:
    integer_types = (int, long)
    string_types = (str, unicode)
except NameError:
    integer_types = (int,)
    string_types = (str,)

VERSION = 1
MAX_JSON_BYTES = 16384
MAX_SOURCE_BYTES = 1024 * 1024
MAX_OBSERVATIONS = 8
TYPE_NAME = 'ussr:MS-1'
SHELLS = (('_37mm_UBRT1', 10, 2570, 'ARMOR_PIERCING'),
          ('_37mm_BPT1', 11, 2826, 'HOLLOW_CHARGE'),
          ('_37mm_UOT1', 12, 3082, 'HIGH_EXPLOSIVE'))
SHELL_CDS = tuple(row[2] for row in SHELLS)
LAYOUT_INDEX = (5891, 5892)
CAPACITY = 96
SOURCE_HASHES = (
    ('res/scripts/common/items/__init__.pyc', '587ba137fee1b7de77ce81d5e963185ba20267c54d157ce8699a76f2f0d11176'),
    ('res/scripts/common/items/vehicles.pyc', '805240e4b59d8a75950dbb97b41c17867606e7e96d7ff0c8d7b05312b83ae8b6'),
    ('res/scripts/common/account_shared.pyc', '187f914c508a359a0fa4f9cc4a0764080a9d71c9214a3b74e9f7ef72cfa6f65c'),
    ('res/scripts/client/CurrentVehicle.pyc', 'a57c32ca6e84c2ae4c343bba3b88213680c65f3a28adb50d8009e0c9df833953'),
    ('res/scripts/client/gui/shared/gui_items/Vehicle.pyc', 'ec78e36ab100e2c2274dd69476da99a26791037c6d79d707921168b1e95ae1e8'),
    ('res/scripts/client/gui/shared/gui_items/vehicle_modules.pyc', '8541c30f9258511e80decb3a5ed5545e59238343ae532e8112895b6539797c7b'),
    ('res/scripts/client/gui/shared/utils/requesters/inventoryrequester.pyc', '4e2c79a4f826740b3363b14b00dba7aeaa9a539dc3c1b32671eb5256f4103e84'),
    ('res/scripts/client/gui/shared/utils/requesters/itemsrequester.pyc', '41e5e9bacbb68e89202116bd267c6cd9fceeda4edb0ed605c7b87cc9315c0c44'),
    ('res/scripts/client/gui/Scaleform/daapi/view/lobby/hangar/ammunitionpanel.pyc', '54d139dd4280314111ce509c15360da8d932cfbc356b30d40c1d9ca96c3addc8'),
    ('res/scripts/client/gui/Scaleform/daapi/view/meta/ammunitionpanelmeta.pyc', 'b8ff5d7e1f986ef9b8165703d42ec6f51f042a485d1004f7a1713eddb73a856a'),
    ('res/scripts/item_defs/vehicles/ussr/ms-1.xml', 'a494bf04d29da7d066fd6923dbb75a79b947559a52405298c494a943c4b0c535'),
    ('res/scripts/item_defs/vehicles/ussr/components/guns.xml', '889fe1564987566478c474ddfef21cbc7742d23bebd19f6a200c59bfafd7d87b'),
    ('res/scripts/item_defs/vehicles/ussr/components/shells.xml', 'ed301edbe07a72b04dc6c6d799bc563de55d0d1f26bd35798354a9f6769e7a96'),
)
_requested = False
_observations = 0


def _integer(value, minimum, maximum, field):
    if type(value) not in integer_types or not minimum <= value <= maximum:
        raise ValueError('bounded native integer required: ' + field)
    return value


def _boolean(value, field):
    if type(value) is not bool:
        raise ValueError('native boolean required: ' + field)
    return value


def _text(value, maximum, field):
    if type(value) is bytes:
        value = value.decode('utf-8', 'strict')
    if type(value) not in string_types or not 1 <= len(value) <= maximum:
        raise ValueError('bounded native text required: ' + field)
    return value


def _map(value, maximum, field):
    if not isinstance(value, dict) or len(value) > maximum:
        raise ValueError('bounded native map required: ' + field)
    return value


def _raw(value, maximum, field):
    if type(value) is not bytes or not 1 <= len(value) <= maximum:
        raise ValueError('original binary string required: ' + field)
    return value


def checked_flat(value, field='shells'):
    """Copy the measured flat pairs; a CD sign is a currency hint, not a count."""
    if type(value) not in (tuple, list) or len(value) > 6 or len(value) % 2:
        raise ValueError('bounded native alternating CD/count sequence required: ' + field)
    copied, seen, total = [], set(), 0
    for index in range(0, len(value), 2):
        compact = _integer(value[index], -65535, 65535, field + '.CD')
        count = _integer(value[index + 1], 0, CAPACITY, field + '.count')
        if abs(compact) not in SHELL_CDS or abs(compact) in seen:
            raise ValueError('incompatible or duplicate native MS-1 shell: ' + field)
        seen.add(abs(compact))
        total += count
        copied.extend((compact, count))
    if total > CAPACITY:
        raise ValueError('native MS-1 ammunition exceeds the audited mounted capacity')
    return copied


def checked_layouts(value):
    rows = []
    for key, flat in _map(value, 8, 'shellsLayout').items():
        if type(key) is not tuple or len(key) != 2:
            raise ValueError('original shellsLayout needs a turret/gun tuple key')
        pair = [_integer(v, 1, 65535, 'layout index') for v in key]
        # This card reads only the fixed stock loadout. Another stored layout is
        # an explicit unsupported input, never silently discarded.
        if tuple(pair) != LAYOUT_INDEX:
            raise ValueError('unexpected additional MS-1 module layout')
        rows.append({'layout_index': pair, 'shells': checked_flat(flat, 'shellsLayout')})
    return sorted(rows, key=lambda row: row['layout_index'])


def _source_hashes(client_root):
    if not os.path.isabs(client_root) or not os.path.isdir(client_root):
        raise ValueError('absolute prepared native client cwd required')
    root = os.path.normcase(os.path.realpath(client_root))
    result = []
    for relative, expected in SOURCE_HASHES:
        path = os.path.join(root, *relative.split('/'))
        resolved = os.path.normcase(os.path.realpath(path))
        if (not resolved.startswith(root + os.sep) or os.path.islink(path)
                or not os.path.isfile(path) or not 1 <= os.path.getsize(path) <= MAX_SOURCE_BYTES):
            raise ValueError('bounded audited original file required: ' + relative)
        with open(path, 'rb') as stream:
            raw = stream.read(MAX_SOURCE_BYTES + 1)
        if not 1 <= len(raw) <= MAX_SOURCE_BYTES:
            raise ValueError('audited original file changed size during read')
        digest = hashlib.sha256(raw).hexdigest()
        if digest != expected:
            raise ValueError('source differs from audited original #717: ' + relative)
        result.append({'relative_path': relative, 'bytes': len(raw), 'sha256': digest})
    return result


def _record_size(payload):
    encoded = json.dumps(payload, ensure_ascii=True, sort_keys=True,
                         separators=(',', ':'), allow_nan=False).encode('ascii')
    if len(encoded) > MAX_JSON_BYTES:
        raise ValueError('bounded MS-1 ammo evidence size exceeded')
    return len(encoded)


def _selection(player, current):
    item = current.item
    if player is None or item is None:
        raise RuntimeError('connected selected native vehicle required')
    return {'database_id': _integer(player.databaseID, 1, 2147483647, 'databaseID'),
            'selected_inventory_id': _integer(current.invID, 1, 2147483647, 'selected ID'),
            'selected_descriptor_sha256': hashlib.sha256(
                _raw(item.descriptor.makeCompactDescr(), 512, 'selected descriptor')).hexdigest()}


def _gui_shells(value):
    if type(value) not in (tuple, list) or len(value) != 3:
        raise ValueError('three original GUI shell objects required')
    result = []
    for item, expected in zip(value, SHELLS):
        compact = _integer(item.intCD, 1, 65535, 'GUI shell CD')
        kind = _text(item.type, 32, 'GUI shell kind')
        if (compact, kind) != (expected[2], expected[3]):
            raise ValueError('original GUI shell order/type differs from mounted shots')
        signed = checked_flat(item.defaultLayoutValue, 'GUI defaultLayoutValue')
        flag = _boolean(item.isBoughtForCredits, 'isBoughtForCredits')
        default_count = _integer(item.defaultCount, 0, CAPACITY, 'defaultCount')
        if signed != [-compact if flag else compact, default_count]:
            raise ValueError('original shell layout getter disagrees with its fields')
        result.append({'compact_descr': compact, 'kind': kind,
                       'count': _integer(item.count, 0, CAPACITY, 'GUI count'),
                       'default_count': default_count, 'is_bought_for_credits': flag,
                       'default_layout_value': signed,
                       'inventory_count': _integer(item.inventoryCount, 0, 2147483647, 'spare count'),
                       'buy_price': _price(item.buyPrice, 'GUI buyPrice'),
                       'default_price': _price(item.defaultPrice, 'GUI defaultPrice')})
    if sum(row['count'] for row in result) > CAPACITY or sum(row['default_count'] for row in result) > CAPACITY:
        raise ValueError('original GUI ammunition exceeds mounted capacity')
    return result


def _price(value, field):
    if type(value) not in (tuple, list) or len(value) != 2:
        raise ValueError('original credits/gold price pair required: ' + field)
    return [_integer(v, 0, 2147483647, field) for v in value]


def _collect_native():
    import BigWorld
    import account_shared
    from items import vehicles, ITEM_TYPES
    from CurrentVehicle import g_currentVehicle
    from gui.shared import g_itemsCache
    from ConnectionManager import connectionManager

    player = BigWorld.player()
    if not connectionManager.isConnected() or not g_itemsCache.isSynced():
        raise RuntimeError('ammo export requires an actual connected synced Account')
    before = _selection(player, g_currentVehicle)
    items = g_itemsCache.items
    inventory = _map(items.inventory.getCacheValue(1, {}), 32, 'vehicle inventory')
    raw_compacts = _map(inventory.get('compDescr'), 8, 'vehicle compact descriptors')
    compact = _raw(raw_compacts.get(1), 512, 'inventory MS-1 descriptor')
    item = items.getVehicle(1)
    desc = item.descriptor
    if (item.invID != 1 or item.intCD != 3329 or desc.type.name != TYPE_NAME
            or tuple(desc.type.id) != (0, 13) or desc.type.compactDescr != 3329
            or ITEM_TYPES.shell != 10 or desc.makeCompactDescr() != compact
            or before['selected_inventory_id'] == 1 and
            before['selected_descriptor_sha256'] != hashlib.sha256(compact).hexdigest()):
        raise ValueError('actual MS-1 identity/descriptor differs from the audited stock vehicle')
    gun, turret = _map(desc.gun, 128, 'mounted gun'), _map(desc.turret, 128, 'mounted turret')
    if (gun['name'] != '_37mm_Gochkins' or gun['compactDescr'] != 5892
            or turret['name'] != 'T-18_Standart' or turret['compactDescr'] != 5891
            or gun['maxAmmo'] != CAPACITY or item.ammoMaxSize != CAPACITY
            or tuple(item.shellsLayoutIdx) != LAYOUT_INDEX):
        raise ValueError('native mounted gun/turret/capacity differs from audited MS-1 override')
    shots = gun['shots']
    if type(shots) not in (tuple, list) or len(shots) != 3:
        raise ValueError('three actual mounted gun shots required')
    shell_rows = []
    for shot, expected in zip(shots, SHELLS):
        shell = _map(_map(shot, 32, 'shot')['shell'], 64, 'shell descriptor')
        if (shell['name'], tuple(shell['id']), shell['compactDescr'], shell['kind']) != (
                expected[0], (0, expected[1]), expected[2], expected[3]):
            raise ValueError('native ordered shell descriptor differs from original resource')
        suitable = vehicles.isShellSuitableForGun(shell['compactDescr'], gun)
        if suitable is not True:
            raise ValueError('original API rejected the mounted compatible shell')
        shell_rows.append({'resource_name': _text(shell['name'], 64, 'shell name'),
                           'item_id': list(shell['id']), 'compact_descr': shell['compactDescr'],
                           'kind': shell['kind'], 'compatible_with_mounted_gun': suitable})
    raw_shells = checked_flat(_map(inventory.get('shells', {}), 8, 'shells column').get(1, []))
    layouts = checked_layouts(_map(inventory.get('shellsLayout', {}), 8, 'layout column').get(1, {}))
    empty = checked_flat(vehicles.getEmptyAmmoForGun(gun), 'native empty ammo')
    default = checked_flat(vehicles.getDefaultAmmoForGun(gun), 'native default ammo')
    gui = _gui_shells(item.shells)
    # These original iterators are read-only. Their actual outputs are included
    # and compared with the native GUI count/default properties.
    parsed_loaded = list(account_shared.AmmoIterator(raw_shells))
    effective_layout = layouts[0]['shells'] if layouts else default
    parsed_layout = list(account_shared.LayoutIterator(effective_layout))
    loaded = dict(parsed_loaded)
    desired = dict((row[0], (row[1], row[2])) for row in parsed_layout)
    storage = _map(items.inventory.getCacheValue(10, {}), 16, 'spare shell inventory')
    storage_rows = []
    for identity in sorted(storage):
        _integer(identity, 1, 65535, 'spare shell CD')
        storage_rows.append({'compact_descr': identity,
                             'count': _integer(storage[identity], 0, 2147483647, 'spare shell count')})
    for row in gui:
        identity = row['compact_descr']
        if (row['count'] != loaded.get(identity, 0)
                or (row['default_count'], row['is_bought_for_credits']) != desired.get(identity, (0, False))
                or row['inventory_count'] != storage.get(identity, 0)):
            raise ValueError('raw inventory/original iterators/GUI shell getters disagree')
    observation = {'raw_shells': raw_shells, 'raw_layouts': layouts,
                   'layout_index': list(item.shellsLayoutIdx), 'mounted_layout_present': bool(layouts),
                   'storage_shells': storage_rows, 'gui_shells': gui,
                   'native_loaded_pairs': [list(pair) for pair in parsed_loaded],
                   'native_layout_rows': [list(row) for row in parsed_layout],
                   'ammo_sum': sum(row['count'] for row in gui),
                   'default_ammo_sum': sum(row['default_count'] for row in gui),
                   'ammo_max_size': _integer(item.ammoMaxSize, 1, 10000, 'ammoMaxSize'),
                   'is_ammo_full': _boolean(item.isAmmoFull, 'isAmmoFull'),
                   'is_auto_load': _boolean(item.isAutoLoad, 'isAutoLoad')}
    after = _selection(BigWorld.player(), g_currentVehicle)
    if (BigWorld.player() is not player or before != after
            or not connectionManager.isConnected() or not g_itemsCache.isSynced()):
        raise RuntimeError('native Account/selection/cache changed during read-only ammo observation')
    return {'version': VERSION, 'type_name': TYPE_NAME, 'type_id': list(desc.type.id),
            'vehicle_inventory_id': item.invID, 'vehicle_type_compact_descr': item.intCD,
            'vehicle_compact_descr_sha256': hashlib.sha256(compact).hexdigest(),
            'turret': {'resource_name': turret['name'], 'compact_descr': turret['compactDescr']},
            'gun': {'resource_name': gun['name'], 'compact_descr': gun['compactDescr']},
            'max_ammo': gun['maxAmmo'], 'shell_item_type': ITEM_TYPES.shell, 'shells': shell_rows,
            'native_empty_ammo': empty, 'native_default_ammo': default, 'observation': observation,
            'selection_before': before, 'selection_after': after, 'selection_unchanged': True,
            'inventory_mutation_requested': False,
            'loaded_module_files': {'vehicles': _text(vehicles.__file__, 1024, 'vehicles module'),
                                    'account_shared': _text(account_shared.__file__, 1024, 'layout module')}}


def export(record):
    """One explicit native read; no server grant and no client state mutation."""
    global _requested
    if _requested or not callable(record):
        raise ValueError('one explicit ammo export and a callable recorder required')
    _requested = True
    try:
        sources = _source_hashes(os.getcwd())
        result = _collect_native()
        result['sources'] = sources
        _record_size(result)
        record('ms1_ammo_descriptors', **result)
        return result
    except Exception:
        record('ms1_ammo_descriptors_error', version=VERSION, traceback=traceback.format_exc()[-8192:])
        raise


def observe(record):
    """Bounded actual raw inventory and original GUI getters; no selection."""
    global _observations
    if not callable(record) or _observations >= MAX_OBSERVATIONS:
        raise ValueError('bounded ammo observer and callable recorder required')
    _observations += 1
    try:
        result = _collect_native()
        result['observation_index'] = _observations
        if _observations == 1:
            result['sources'] = _source_hashes(os.getcwd())
        _record_size(result)
        record('ms1_ammo_observation', **result)
        return result
    except Exception:
        record('ms1_ammo_observation_error', version=VERSION, observation_index=_observations,
               traceback=traceback.format_exc()[-8192:])
        raise
