# -*- coding: utf-8 -*-
"""Opt-in #717 original MS-1 crew export, version 1.

Creates only local descriptor objects through the original client API. No
account, inventory, selection, RPC, UI action or random-generator mutation.
The caller runs export(record) once after a real connected ready Hangar.
Pure helper tests establish bounds, never native compatibility.
"""
import binascii
import hashlib
import json
import math
import os
import traceback

try:
    integer_types = (int, long)
    string_types = (str, unicode)
except NameError:
    integer_types = (int,)
    string_types = (str,)

VERSION = 1
MAX_SOURCE_BYTES = 1024 * 1024
MAX_JSON_BYTES = 16 * 1024
TYPE_NAME = 'ussr:MS-1'
CREW_ROLES = (('commander', 'gunner', 'radioman', 'loader'), ('driver',))
SOURCE_HASHES = (
    ('res/scripts/common/items/tankmen.pyc',
     '74f914b1e5e7e574086dd865d87e4cfbf8cace6e60b5e506757eba28ca8bc530'),
    ('res/scripts/common/items/__init__.pyc',
     '587ba137fee1b7de77ce81d5e963185ba20267c54d157ce8699a76f2f0d11176'),
    ('res/scripts/common/dossiers2/__init__.pyc',
     '7aa74deb47f9718f4eae0d331da2e8ef07ac4e4673b1ec49ab72ee4c1ab58d3b'),
    ('res/scripts/common/dossiers2/custom/builders.pyc',
     'e973a914947a4183946494afe566e8e9118c6f2c27448c8e74bf772aae5a76c6'),
    ('res/scripts/common/dossiers2/common/dossierbuilder.pyc',
     'eed33c28730668a7da5bf7fe6a5a74ac2d0dfd83be5c32a55ff365652aab157e'),
    ('res/scripts/common/dossiers2/common/dossierdescr.pyc',
     '7396051744955d9911490d1b73a7fa7cd286915764c07a52e9743ab65a712179'),
    ('res/scripts/item_defs/tankmen/tankmen.xml',
     'a8604e50bf829072d083535ea3339302a1584582d42e62814a3a871e310ea73b'),
    ('res/scripts/item_defs/tankmen/ussr.xml',
     '7277417f9ffac7f742cd6b1bfce02cc7a182558fbdf7db137604323403552cee'),
    ('res/scripts/item_defs/vehicles/ussr/MS-1.xml',
     'a494bf04d29da7d066fd6923dbb75a79b947559a52405298c494a943c4b0c535'),
)
_requested = False
_observations = 0


def _integer(value, lower, upper, field):
    if type(value) not in integer_types or not lower <= value <= upper:
        raise ValueError('bounded integer required: ' + field)
    return value


def _raw(value, lower, upper, field):
    if type(value) is not bytes or not lower <= len(value) <= upper:
        raise ValueError('bounded original binary string required: ' + field)
    return value


def _text(value, maximum, field):
    if type(value) not in string_types or not 1 <= len(value) <= maximum:
        raise ValueError('bounded original text required: ' + field)
    return value


def _ids(values, field):
    if type(values) not in (tuple, list) or not 2 <= len(values) <= 2048:
        raise ValueError('bounded original passport ID list required: ' + field)
    result = [_integer(value, 0, 65535, field) for value in values]
    if len(set(result)) != len(result):
        raise ValueError('duplicate original passport ID: ' + field)
    return sorted(result)


def choose_passports(config):
    """Choose IDs from actual normalGroups without calling random.choice.

    The audited Russian resource has one male normal group. This narrow
    exporter rejects a different resource shape rather than guessing a group.
    It does not modify or serialize the configuration's rich native objects.
    """
    if type(config) is not dict or len(config) > 32:
        raise ValueError('bounded original nation config required')
    groups = config.get('normalGroups')
    if type(groups) not in (tuple, list) or len(groups) != 1:
        raise ValueError('expected the one audited Russian normal group')
    group = groups[0]
    if type(group) is not dict or len(group) > 16 or group.get('isFemales') is not False:
        raise ValueError('unexpected audited Russian passport group')
    identifiers = []
    for list_name, map_name in (('firstNamesList', 'firstNames'),
                                ('lastNamesList', 'lastNames'), ('iconsList', 'icons')):
        values = _ids(group.get(list_name), list_name)
        mapping = config.get(map_name)
        if type(mapping) is not dict or not 2 <= len(mapping) <= 4096:
            raise ValueError('bounded original passport map required: ' + map_name)
        if any(value not in mapping for value in values):
            raise ValueError('original passport ID missing from nation map')
        identifiers.append(values)
    return [(0, False, False, identifiers[0][i], identifiers[1][i], identifiers[2][i])
            for i in range(2)]


def _source_hashes(client_root):
    """Read fixed files only; the caller's prepared client cwd is required."""
    if not os.path.isabs(client_root) or not os.path.isdir(client_root):
        raise ValueError('absolute native client cwd required')
    root = os.path.normcase(os.path.realpath(client_root))
    records = []
    for relative, expected in SOURCE_HASHES:
        path = os.path.join(root, *relative.split('/'))
        resolved = os.path.normcase(os.path.realpath(path))
        if (not resolved.startswith(root + os.sep) or os.path.islink(path) or
                not os.path.isfile(path) or not 1 <= os.path.getsize(path) <= MAX_SOURCE_BYTES):
            raise ValueError('expected bounded local original resource: ' + relative)
        with open(path, 'rb') as stream:
            raw = stream.read(MAX_SOURCE_BYTES + 1)
        if not 1 <= len(raw) <= MAX_SOURCE_BYTES:
            raise ValueError('original resource changed size while reading')
        actual = hashlib.sha256(raw).hexdigest()
        if actual != expected:
            raise ValueError('source differs from audited original #717: ' + relative)
        records.append({'relative_path': relative, 'bytes': len(raw), 'sha256': actual})
    return records


def _decoded_values(desc, passport, role):
    """Read only the documented native descriptor scalar fields."""
    values = {
        'nation_id': _integer(desc.nationID, 0, 15, 'nationID'),
        'vehicle_type_id': _integer(desc.vehicleTypeID, 0, 255, 'vehicleTypeID'),
        'role': _text(desc.role, 16, 'role'),
        'role_level': _integer(desc.roleLevel, 0, 100, 'roleLevel'),
        'free_xp': _integer(desc.freeXP, 0, 2147483647, 'freeXP'),
        'total_xp': _integer(desc.totalXP(), 0, 2147483647, 'native totalXP'),
        'last_skill_level': _integer(desc.lastSkillLevel, 0, 100, 'lastSkillLevel'),
        'first_name_id': _integer(desc.firstNameID, 0, 65535, 'firstNameID'),
        'last_name_id': _integer(desc.lastNameID, 0, 65535, 'lastNameID'),
        'icon_id': _integer(desc.iconID, 0, 65535, 'iconID'),
        'rank_id': _integer(desc.rankID, 0, 65535, 'rankID'),
        'levels_to_next_rank': _integer(desc.numLevelsToNextRank, 0, 2047, 'numLevelsToNextRank'),
    }
    if (type(desc.skills) not in (list, tuple) or len(desc.skills) != 0 or
            desc.isPremium is not False or desc.isFemale is not False):
        raise ValueError('native descriptor differs from unskilled normal test crew')
    values.update(skills=[], is_premium=False, is_female=False)
    actual = (values['nation_id'], False, False, values['first_name_id'],
              values['last_name_id'], values['icon_id'])
    if (actual != passport or values['vehicle_type_id'] != 13 or values['role'] != role or
            values['role_level'] != 100 or values['free_xp'] != 0 or
            values['last_skill_level'] != 0):
        raise ValueError('original round-trip changed requested test crew properties')
    return values


def _record_size(payload):
    encoded = json.dumps(payload, ensure_ascii=True, sort_keys=True,
                         separators=(',', ':')).encode('ascii')
    if len(encoded) > MAX_JSON_BYTES:
        raise ValueError('MS-1 crew observation exceeds bounded record size')
    return len(encoded)


def export(record):
    """One-shot original constructor/readback; emits primitives, grants nothing."""
    global _requested
    if _requested or not callable(record):
        raise ValueError('one MS-1 crew export with a callable recorder is required')
    _requested = True
    try:
        sources = _source_hashes(os.getcwd())
        import BigWorld
        import dossiers2
        from items import vehicles, tankmen, ITEM_TYPES
        from CurrentVehicle import g_currentVehicle
        from gui.shared import g_itemsCache
        from ConnectionManager import connectionManager

        def selection():
            player, current = BigWorld.player(), g_currentVehicle.item
            if (player is None or current is None or not connectionManager.isConnected() or
                    not g_itemsCache.isSynced()):
                raise RuntimeError('original crew export requires a connected selected vehicle')
            raw = _raw(current.descriptor.makeCompactDescr(), 1, 512, 'selected vehicle')
            return {'database_id': _integer(player.databaseID, 1, 2147483647, 'databaseID'),
                    'selected_inventory_id': _integer(g_currentVehicle.invID, 1, 2147483647, 'inventoryID'),
                    'selected_descriptor_sha256': hashlib.sha256(raw).hexdigest()}

        before = selection()
        vehicle = vehicles.VehicleDescr(typeName=TYPE_NAME)
        if (tuple(vehicles.g_list.getIDsByName(TYPE_NAME)) != (0, 13) or
                tuple(vehicle.type.id) != (0, 13) or vehicle.type.name != TYPE_NAME or
                vehicle.type.compactDescr != 3329 or ITEM_TYPES.tankman != 8 or
                tuple(tuple(slot) for slot in vehicle.type.crewRoles) != CREW_ROLES):
            raise ValueError('native vehicle/crew schema differs from audited MS-1')
        passports = choose_passports(tankmen.getNationConfig(0))
        dossier = _raw(dossiers2.getTankmanDossierDescr('').makeCompDescr(), 1, 2048,
                       'original empty tankman dossier')
        dossier_hash = hashlib.sha256(dossier).hexdigest()
        crew = []
        for slot, passport in enumerate(passports):
            role = CREW_ROLES[slot][0]
            compact = _raw(tankmen.generateCompactDescr(passport, 13, role, 100, [], 0, dossier),
                           19, 4096, 'original tankman descriptor')
            decoded = tankmen.TankmanDescr(compactDescr=compact, battleOnly=False)
            values = _decoded_values(decoded, passport, role)
            repacked = _raw(decoded.makeCompactDescr(), 19, 4096, 'repacked tankman descriptor')
            if (repacked != compact or decoded.dossierCompactDescr != dossier or
                    dossiers2.getTankmanDossierDescr(decoded.dossierCompactDescr).makeCompDescr() != dossier):
                raise ValueError('original compact/dossier round-trip mismatch')
            crew.append({'slot_index': slot, 'role': role,
                         'combined_roles': list(CREW_ROLES[slot]),
                         'compact_descr_hex': binascii.hexlify(compact).decode('ascii'),
                         'compact_descr_sha256': hashlib.sha256(compact).hexdigest(),
                         'compact_descr_bytes': len(compact), 'decoded': values,
                         'dossier_sha256': dossier_hash, 'original_parse_repack_equal': True,
                         'original_dossier_repack_equal': True})
        after = selection()
        if before != after:
            raise RuntimeError('selected account/vehicle changed during readonly crew export')
        payload = {'version': VERSION, 'type_name': TYPE_NAME, 'type_id': [0, 13],
                   'vehicle_type_compact_descr': 3329, 'tankman_item_type': ITEM_TYPES.tankman,
                   'policy': 'test_lab_role_level_100_no_skills', 'crew': crew,
                   'tankman_dossier_hex': binascii.hexlify(dossier).decode('ascii'),
                   'tankman_dossier_sha256': dossier_hash, 'sources': sources,
                   'selection_before': before, 'selection_after': after,
                   'selection_unchanged': True, 'inventory_mutation_requested': False,
                   'loaded_module_files': {
                       'tankmen': _text(tankmen.__file__, 1024, 'tankmen module file'),
                       'vehicles': _text(vehicles.__file__, 1024, 'vehicles module file'),
                       'dossiers2': _text(dossiers2.__file__, 1024, 'dossiers module file')}}
        _record_size(payload)
        record('ms1_crew_descriptors', **payload)
        return payload
    except Exception:
        record('ms1_crew_descriptors_error', version=VERSION,
               traceback=traceback.format_exc()[-8192:])
        raise


def _number(value, lower, upper, field):
    if (type(value) not in integer_types + (float,) or
            not lower <= value <= upper or
            (type(value) is float and (math.isnan(value) or math.isinf(value)))):
        raise ValueError('bounded finite native number required: ' + field)
    return value


def _native_text(value, maximum, field):
    if type(value) is bytes:
        value = value.decode('utf-8', 'strict')
    return _text(value, maximum, field)


def _observed_tankman(item):
    compact = _raw(item.strCD, 19, 4096, 'inventory tankman strCD')
    desc = item.descriptor
    passport = (desc.nationID, desc.isPremium, desc.isFemale,
                desc.firstNameID, desc.lastNameID, desc.iconID)
    decoded = _decoded_values(desc, passport, desc.role)
    if desc.makeCompactDescr() != compact:
        raise ValueError('observed original tankman parse/repack mismatch')
    real = item.realRoleLevel
    if (type(real) not in (tuple, list) or len(real) != 2 or
            type(real[1]) not in (tuple, list) or len(real[1]) != 5):
        raise ValueError('unexpected original effective-role tuple')
    bonuses = dict((name, _number(value, -1000, 1000, name))
                   for name, value in zip(('commander', 'brotherhood', 'equipment',
                                           'opt_devices', 'penalty'), real[1]))
    combined = item.combinedRoles
    if (type(combined) not in (tuple, list) or not 1 <= len(combined) <= 5 or
            any(role not in ('commander', 'gunner', 'driver', 'radioman', 'loader')
                for role in combined)):
        raise ValueError('unexpected observed combined roles')
    in_tank = item.isInTank
    if type(in_tank) is not bool:
        raise ValueError('native isInTank must be a boolean')
    return {'inventory_id': _integer(item.invID, 1, 2147483647, 'tankman inventory ID'),
            'vehicle_inventory_id': _integer(item.vehicleInvID, -1, 2147483647, 'owning vehicle ID'),
            'vehicle_slot_index': _integer(item.vehicleSlotIdx, -1, 15, 'owning vehicle slot'),
            'is_in_tank': in_tank, 'combined_roles': list(combined), 'decoded': decoded,
            'compact_descr_hex': binascii.hexlify(compact).decode('ascii'),
            'compact_descr_sha256': hashlib.sha256(compact).hexdigest(),
            'compact_descr_bytes': len(compact), 'original_parse_repack_equal': True,
            'dossier_sha256': hashlib.sha256(_raw(desc.dossierCompactDescr, 1, 2048,
                                                 'observed embedded dossier')).hexdigest(),
            'first_name': _native_text(item.firstUserName, 128, 'first name'),
            'last_name': _native_text(item.lastUserName, 128, 'last name'),
            'rank_name': _native_text(item.rankUserName, 128, 'rank name'),
            'portrait_icon': _native_text(item.icon, 256, 'portrait icon'),
            'base_role_level': _integer(item.roleLevel, 0, 100, 'base role level'),
            'efficiency_role_level': _number(item.efficiencyRoleLevel, 0, 1000, 'efficiency role level'),
            'effective_role_level': _number(real[0], 0, 1000, 'effective role level'),
            'bonuses': bonuses}


def _observed_vehicle(item):
    crew, slots = item.crew, []
    if type(crew) not in (tuple, list) or not 1 <= len(crew) <= 8:
        raise ValueError('bounded original vehicle crew slots required')
    roles = item.descriptor.type.crewRoles
    if type(roles) not in (tuple, list) or len(roles) != len(crew):
        raise ValueError('original vehicle crew/roles count mismatch')
    for pair in crew:
        if type(pair) not in (tuple, list) or len(pair) != 2:
            raise ValueError('original vehicle crew must contain slot/Tankman pairs')
        slot, tankman = pair
        _integer(slot, 0, len(crew) - 1, 'vehicle crew slot')
        if type(roles[slot]) not in (tuple, list) or not 1 <= len(roles[slot]) <= 5:
            raise ValueError('bounded original vehicle slot roles required')
        slots.append({'slot_index': slot, 'role': _text(roles[slot][0], 16, 'slot role'),
                      'tankman_inventory_id': None if tankman is None else
                      _integer(tankman.invID, 1, 2147483647, 'assigned tankman ID'),
                      'tankman_compact_descr_sha256': None if tankman is None else
                      hashlib.sha256(_raw(tankman.strCD, 19, 4096, 'assigned tankman strCD')).hexdigest()})
    if sorted(row['slot_index'] for row in slots) != list(range(len(crew))):
        raise ValueError('duplicate or missing original vehicle crew slot')
    raw = _raw(item.descriptor.makeCompactDescr(), 1, 512, 'inventory vehicle descriptor')
    return {'inventory_id': _integer(item.invID, 1, 2147483647, 'vehicle inventory ID'),
            'type_name': _text(item.descriptor.type.name, 128, 'vehicle type name'),
            'type_compact_descr': _integer(item.intCD, 1, 2147483647, 'vehicle type compact descriptor'),
            'descriptor_sha256': hashlib.sha256(raw).hexdigest(),
            'crew': sorted(slots, key=lambda row: row['slot_index'])}


def crew_status(tankmen, vehicles):
    """Check assignment-only primitive observations; not a native/UI verdict.

    Independent acceptance must also compare the raw descriptors with the
    server's immutable fixture and prove the selected MS-1 and real crew GUI.
    """
    if (type(tankmen) is not list or len(tankmen) > 16 or
            type(vehicles) is not list or len(vehicles) != 2):
        raise ValueError('bounded two-vehicle observation required')
    vehicle_map = dict((row['inventory_id'], row) for row in vehicles)
    if set(vehicle_map) != set((1, 2)):
        raise ValueError('expected both actual inventory vehicles')
    ids = [_integer(row['inventory_id'], 1, 2147483647, 'observed tankman ID') for row in tankmen]
    if len(set(ids)) != len(ids):
        raise ValueError('duplicate observed tankman inventory ID')
    issues = []
    if len(tankmen) != 2:
        issues.append('crew_not_granted' if not tankmen else 'tankman_count_not_two')
    ms1, is7 = vehicle_map[1], vehicle_map[2]
    if (ms1['type_compact_descr'] != 3329 or is7['type_compact_descr'] != 7169 or
            len(ms1['crew']) != 2 or len(is7['crew']) != 5):
        raise ValueError('actual vehicle types or crew capacities changed')
    if (sorted(slot['slot_index'] for slot in ms1['crew']) != [0, 1] or
            sorted(slot['slot_index'] for slot in is7['crew']) != list(range(5))):
        raise ValueError('duplicate or missing observed crew slots')
    if (any(slot['tankman_inventory_id'] is not None for slot in is7['crew'])):
        issues.append('is7_crew_must_remain_empty')
    by_id = dict((row['inventory_id'], row) for row in tankmen)
    assigned = []
    for slot in ms1['crew']:
        index, identity = slot['slot_index'], slot['tankman_inventory_id']
        _integer(index, 0, 1, 'MS-1 slot index')
        if identity is None:
            issues.append('ms1_slot_%d_empty' % index)
            continue
        assigned.append(identity)
        row = by_id.get(identity)
        if row is None:
            issues.append('ms1_slot_%d_missing_tankman' % index)
            continue
        desc = row['decoded']
        if (row['vehicle_inventory_id'] != 1 or row['vehicle_slot_index'] != index or
                row['is_in_tank'] is not True or row['combined_roles'] != list(CREW_ROLES[index]) or
                slot['role'] != CREW_ROLES[index][0] or desc['role'] != CREW_ROLES[index][0] or
                row['compact_descr_sha256'] != slot['tankman_compact_descr_sha256']):
            issues.append('ms1_slot_%d_assignment_mismatch' % index)
        if (desc['nation_id'] != 0 or desc['vehicle_type_id'] != 13 or desc['role_level'] != 100 or
                desc['free_xp'] != 0 or desc['skills'] != [] or desc['last_skill_level'] != 0 or
                desc['is_premium'] is not False or desc['is_female'] is not False):
            issues.append('ms1_slot_%d_policy_mismatch' % index)
    if len(assigned) != 2 or len(set(assigned)) != 2 or set(assigned) != set(ids):
        issues.append('ms1_assignments_not_exact_inventory')
    return {'ready': not issues, 'issues': issues, 'tankmen_count': len(tankmen),
            'ms1_assigned_ids': assigned, 'is7_assigned_count': sum(
                slot['tankman_inventory_id'] is not None for slot in is7['crew'])}


def _vehicle_inventory_ids(inventory):
    """Read IDs from original getCacheValue(VEHICLE), never type-CD cache keys.

    Original InventoryRequester.getItemsData line94 returns a prepared cache
    keyed by typeCompDescr. Its own initial read uses getCacheValue and the
    compDescr column; only that column is keyed by vehicle inventory ID.
    """
    if not isinstance(inventory, dict) or not 1 <= len(inventory) <= 32:
        raise ValueError('bounded original vehicle inventory field map required')
    compacts = inventory.get('compDescr')
    if not isinstance(compacts, dict) or len(compacts) != 2:
        raise ValueError('expected both original vehicle inventory descriptors')
    identities = [_integer(identity, 1, 2147483647, 'vehicle inventory key')
                  for identity in compacts]
    if set(identities) != set((1, 2)):
        raise ValueError('expected exactly the existing MS-1 and IS-7 inventory')
    return tuple(sorted(identities))


def observe(record):
    """Read both actual vehicles and native inventory Tankmen; never select one."""
    global _observations
    if not callable(record) or _observations >= 8:
        raise ValueError('bounded crew observer with a callable recorder is required')
    _observations += 1
    try:
        import BigWorld
        from CurrentVehicle import g_currentVehicle
        from gui.shared import g_itemsCache
        from ConnectionManager import connectionManager
        player = BigWorld.player()
        if player is None or not connectionManager.isConnected() or not g_itemsCache.isSynced():
            raise RuntimeError('crew observation requires a real connected synced account')
        database_id = _integer(player.databaseID, 1, 2147483647, 'databaseID')
        selected = _integer(g_currentVehicle.invID, 1, 2147483647, 'selected vehicle ID')
        items = g_itemsCache.items
        vehicle_ids = _vehicle_inventory_ids(items.inventory.getCacheValue(1, {}))
        actual = items.getTankmen()
        if not isinstance(actual, dict) or len(actual) > 16:
            raise ValueError('bounded original tankmen collection required')
        rows = []
        for identity in sorted(actual):
            _integer(identity, 1, 2147483647, 'tankman collection key')
            row = _observed_tankman(actual[identity])
            if row['inventory_id'] != identity:
                raise ValueError('tankman collection key/identity mismatch')
            rows.append(row)
        vehicles = [_observed_vehicle(items.getVehicle(identity)) for identity in vehicle_ids]
        result = crew_status(rows, vehicles)
        if (BigWorld.player() is not player or player.databaseID != database_id or
                g_currentVehicle.invID != selected or not g_itemsCache.isSynced()):
            raise RuntimeError('account/selection/cache changed during crew observation')
        result.update(version=VERSION, observation_index=_observations,
                      database_id=database_id, selected_inventory_id=selected,
                      selected_ms1=selected == 1, tankmen=rows, vehicles=vehicles,
                      inventory_mutation_requested=False, selection_changed_by_observer=False)
        _record_size(result)
        record('ms1_crew_observation', **result)
        return result
    except Exception:
        record('ms1_crew_observation_error', version=VERSION,
               observation_index=_observations, traceback=traceback.format_exc()[-8192:])
        raise
