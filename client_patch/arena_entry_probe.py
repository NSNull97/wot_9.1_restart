# -*- coding: utf-8 -*-
"""Opt-in passive #717 arena resource and native Entity observations.

This module never constructs an Entity, invokes a lifecycle callback, changes
selection, sends an RPC, creates geometry, or quits. The host owns the explicit
diagnostic condition and separately records original native lifecycle frames.
An Avatar constructor is a checkpoint, not proof of a loaded arena or a battle.
"""
import hashlib
import json
import math
import os

try:
    integer_types = (int, long)
    string_types = (str, unicode)
except NameError:
    integer_types = (int,)
    string_types = (str,)

VERSION = 1
MAX_JSON_BYTES = 8192
MAX_SOURCE_BYTES = 1024 * 1024
MAX_OBSERVATIONS = 240
ARENA_TYPE_ID = 1
GEOMETRY_NAME = '01_karelia'
GEOMETRY_PATH = 'spaces/01_karelia'
SOURCE_HASHES = (
    ('res/scripts/client/Avatar.pyc', 'c13cd58a4c5d766dfd3c5f47ae7be50c962aee6c7f8cf25b4341322381f21e0e'),
    ('res/scripts/client/ClientArena.pyc', '30b21bb0e386b909d162f127b79b86e5da1aeecb65e9c6700b2b50f435dbd455'),
    ('res/scripts/common/ArenaType.pyc', '9b1255ac3cd08f23b429570c229337c80286253b4a97b5bf82c3c6f3744adfa0'),
    ('res/scripts/common/constants.pyc', '1c07c2e6a956dcfef95c4020954b4ca39efd77844d328cded935307a6515eebd'),
    ('res/scripts/client/gui/arena_info/listeners.pyc', '3bffa4ccb310300b27610a93a80363817989b80734b33f0c3d012c3302799192'),
    ('res/scripts/client/gui/arena_info/ArenaLoadController.pyc', 'fbfd0aa54d2b165c3f03dbad1499a5d2c689390f65307d038f2ece0424da6228'),
    ('res/scripts/arena_defs/_list_.xml', '5d3c9d7b9d73125c86013f16d899b50045c23b7af8b7fe490824e58b7ad85421'),
    ('res/scripts/arena_defs/_default_.xml', 'd837cdd2558ef5cfca90b3d2d1d78a60b73f7be1f4ada5f686f3c97f5c48171a'),
    ('res/scripts/arena_defs/01_karelia.xml', '8afc7d150c12b616246260e12158b2126be2872041a38603cbdf0c9a779d6bdb'),
    ('res/scripts/entity_defs/Avatar.def', '38cf983d6ea1fcaf1bbca25fd18567fed5abc3b2e07fbe14b168f46fa883f74d'),
    ('res/scripts/entity_defs/Vehicle.def', '08dc1e6be577f80a04bf813ca046550201a3c4e673dad1540c5f1c6a047d1297'),
)
# Attribute, actual co_name, line, argcount, co_code SHA. These are measured
# original methods. Returning from a profiler event is independently checked by
# the host; these code hashes do not assert that a method has actually run.
AVATAR_METHODS = (
    ('__init__', '__init__', 110, 1, '9ed1152053fa15094d0452ae3653564dab0b55a2e3c50afed13561c2d997a846'),
    ('onBecomePlayer', 'onBecomePlayer', 147, 1, '98f0ac96522e86be7475e4b6721c99fccd9acdb1142f372d29826ffddcc99b94'),
    ('onEnterWorld', 'onEnterWorld', 388, 2, '44ab19cd3b64ec7e6f8f347f9d5229183734e1eb4bc1db251bcc14f9fd13a57d'),
    ('onSpaceLoaded', 'onSpaceLoaded', 535, 1, '1c77d2ce95d5e6d39651998ac2f306c8da44cc9862a9a6fcf255c9890b690f5d'),
    ('_PlayerAvatar__onInitStepCompleted', '__onInitStepCompleted', 2579, 1, 'a4e31915434196e76c800e7c6713f1f49fa2eec08b097b5d0a40875df7324475'),
    ('userSeesWorld', 'userSeesWorld', 1086, 1, '2652cc2e7750e94fa850bd40d88c0d7be855637169155775937263ae73be980b'),
    ('onBecomeNonPlayer', 'onBecomeNonPlayer', 361, 1, '3d3335b785c4088a2688691385ee84fa7612bea99a25b68f72f2cf01ee049ab4'),
    ('onLeaveWorld', 'onLeaveWorld', 425, 1, 'aaec3ec6ee7c8f8975348df4c252cbabf1015d795ff24aeb39351456094a5cc6'),
)
_export_requested = False
_provenance_checked = False
_observations = 0


def _integer(value, low, high, label):
    if type(value) not in integer_types or not low <= value <= high:
        raise ValueError('bounded native integer required: ' + label)
    return value


def _number(value, low, high, label):
    if type(value) not in integer_types + (float,) or not low <= value <= high:
        raise ValueError('bounded finite native number required: ' + label)
    value = float(value)
    if math.isnan(value) or math.isinf(value):
        raise ValueError('finite native number required: ' + label)
    return value


def _boolean(value, label):
    if type(value) is not bool:
        raise ValueError('native boolean required: ' + label)
    return value


def _text(value, limit, label):
    if type(value) is bytes:
        value = value.decode('utf-8', 'strict')
    if type(value) not in string_types or not 1 <= len(value) <= limit:
        raise ValueError('bounded native text required: ' + label)
    if len(value.encode('utf-8')) > limit * 4:
        raise ValueError('native text byte bound exceeded: ' + label)
    return value


def _emit(record, event, data):
    raw = json.dumps(data, ensure_ascii=True, sort_keys=True,
                     separators=(',', ':'), allow_nan=False).encode('ascii')
    if len(raw) > MAX_JSON_BYTES:
        raise ValueError('arena evidence exceeds its 8 KiB bound')
    record(event, **data)
    return data


def _source_hashes(root):
    if not os.path.isabs(root) or not os.path.isdir(root):
        raise ValueError('absolute prepared client cwd required')
    root = os.path.normcase(os.path.realpath(root))
    result = []
    for relative, expected in SOURCE_HASHES:
        path = os.path.join(root, *relative.split('/'))
        resolved = os.path.normcase(os.path.realpath(path))
        if (not resolved.startswith(root + os.sep) or os.path.islink(path)
                or not os.path.isfile(path)
                or not 1 <= os.path.getsize(path) <= MAX_SOURCE_BYTES):
            raise ValueError('bounded original file required: ' + relative)
        with open(path, 'rb') as stream:
            raw = stream.read(MAX_SOURCE_BYTES + 1)
        if not 1 <= len(raw) <= MAX_SOURCE_BYTES:
            raise ValueError('original file changed size while reading')
        digest = hashlib.sha256(raw).hexdigest()
        if digest != expected:
            raise ValueError('arena source differs from original #717: ' + relative)
        result.append({'relative_path': relative, 'bytes': len(raw), 'sha256': digest})
    return result


def _code_contract(function, expected, filename='scripts/client/Avatar.py'):
    function = getattr(function, 'im_func', function)
    code = getattr(function, 'func_code', getattr(function, '__code__', None))
    if code is None:
        raise ValueError('original Python method required')
    _, name, line, argcount, digest = expected
    if (code.co_filename.replace('\\', '/') != filename or code.co_name != name
            or code.co_firstlineno != line or code.co_argcount != argcount
            or hashlib.sha256(code.co_code).hexdigest() != digest):
        raise ValueError('original arena callback binding differs: ' + name)


def _audit_avatar_bindings(avatar_class):
    for expected in AVATAR_METHODS:
        _code_contract(getattr(avatar_class, expected[0]), expected)


def _account_identity(player, account_class):
    if type(player) is not account_class:
        raise RuntimeError('native resource export requires the original PlayerAccount')
    return {'database_id': _integer(player.databaseID, 1, 2147483647, 'databaseID'),
            'entity_id': _integer(player.id, 1, 2147483647, 'entityID'),
            'name': _text(player.name, 128, 'account name')}


def _collect_resources():
    import Account
    import Avatar
    import ArenaType
    import BigWorld
    import ResMgr
    from ConnectionManager import connectionManager
    if not connectionManager.isConnected():
        raise RuntimeError('native connected Account required for arena export')
    before = _account_identity(BigWorld.player(), Account.PlayerAccount)
    if Account.g_accountRepository is None:
        raise RuntimeError('original Account repository is required')
    _audit_avatar_bindings(Avatar.PlayerAvatar)
    if not isinstance(ArenaType.g_cache, dict) or not 1 <= len(ArenaType.g_cache) <= 1024:
        raise ValueError('bounded initialized original ArenaType cache required')
    arena = ArenaType.g_cache[ARENA_TYPE_ID]
    if (type(arena) is not ArenaType.ArenaType or arena.id != ARENA_TYPE_ID
            or arena.geometryID != 1 or arena.gameplayID != 0
            or arena.geometryName != GEOMETRY_NAME or arena.geometry != GEOMETRY_PATH
            or arena.gameplayName != 'ctf'):
        raise ValueError('native arena candidate differs from the original list/config')
    bounds = arena.boundingBox
    if type(bounds) not in (tuple, list) or len(bounds) != 2:
        raise ValueError('two original map bounding-box vectors required')
    box = [[_number(v.x, -10000, 10000, 'map X'),
            _number(v.y, -10000, 10000, 'map Z')] for v in bounds]
    if box != [[-500.0, -500.0], [500.0, 500.0]]:
        raise ValueError('candidate arena bounds differ from original XML')
    weather = arena.weatherPresets
    if type(weather) not in (tuple, list) or len(weather) != 1 or weather[0] != {'rnd_range': (0, 1)}:
        raise ValueError('candidate weather defaults differ from original resource reader')
    section = ResMgr.openSection(GEOMETRY_PATH + '/space.settings')
    if section is None:
        raise RuntimeError('native resource manager cannot read candidate space.settings')
    after = _account_identity(BigWorld.player(), Account.PlayerAccount)
    if before != after:
        raise RuntimeError('native player changed during read-only resource export')
    return {'version': VERSION, 'account_before': before, 'account_after': after,
            'arena_type_id': arena.id, 'geometry_id': arena.geometryID,
            'gameplay_id': arena.gameplayID, 'gameplay_name': _text(arena.gameplayName, 32, 'gameplay'),
            'geometry_name': _text(arena.geometryName, 64, 'geometry name'),
            'geometry_path': _text(arena.geometry, 128, 'geometry path'),
            'native_display_name': _text(arena.name, 128, 'native map name'),
            'public_project_name': None, 'public_project_name_approved': False,
            'bounding_box': box, 'weather_preset_count': len(weather),
            'space_settings_present': True, 'selection_changed_by_probe': False,
            'native_entity_created_by_probe': False, 'arena_loaded_proven': False}


def export(record):
    """One resource export from original getters; it does not load an arena."""
    global _export_requested, _provenance_checked
    if _export_requested:
        raise RuntimeError('arena resource export already requested')
    _export_requested = True
    sources = _source_hashes(os.getcwd())
    data = _collect_resources()
    data['sources'] = sources
    result = _emit(record, 'arena_entry_resources', data)
    _provenance_checked = True
    return result


def _optional(obj, attribute, label, validator, unavailable, none_is_unavailable=False):
    # A base-only Entity can legitimately lack cell properties. Record absence
    # explicitly; do not substitute zero/False or suppress a failing getter.
    try:
        value = getattr(obj, attribute)
    except AttributeError:
        unavailable.append(label)
        return None
    if value is None and none_is_unavailable:
        # Measured #717 base-only PlayerAvatar.spaceID is present but None.
        # This opt-in never turns a missing cell/space into synthetic ID zero.
        unavailable.append(label)
        return None
    return validator(value, label)


def _position(value, label):
    return [_number(value.x, -10000000, 10000000, label + '.x'),
            _number(value.y, -10000000, 10000000, label + '.y'),
            _number(value.z, -10000000, 10000000, label + '.z')]


def _collect_observation():
    import Account
    import Avatar
    import BigWorld
    import ClientArena
    import Vehicle
    from ConnectionManager import connectionManager
    _audit_avatar_bindings(Avatar.PlayerAvatar)
    player = BigWorld.player()
    repository = Account.g_accountRepository
    data = {'version': VERSION, 'native_connected': bool(connectionManager.isConnected()),
            'player_present': player is not None,
            'repository_present': repository is not None,
            'repository_owner_id': id(repository) if repository is not None else None,
            'player_class': None, 'player_module': None, 'player_owner_id': None,
            'player_is_original_avatar': False, 'player_is_original_account': False,
            'entity_id': None, 'name': None, 'space_id': None, 'position': None,
            'in_world': None, 'steps_till_init': None, 'space_initialized': None,
            'user_sees_world': None, 'world_draw_enabled': None, 'space_load_progress': None,
            'arena_present': False, 'arena_type_id': None, 'arena_unique_id': None,
            'geometry_name': None, 'geometry_path': None, 'arena_vehicle_count': None,
            'player_vehicle_id': None, 'vehicle_present': False,
            'vehicle_is_original': False, 'vehicle_in_world': None,
            'vehicle_descriptor_present': False, 'unavailable': [],
            'acceptance': 'OBSERVATION_ONLY'}
    if player is None:
        return data
    data.update(player_class=_text(type(player).__name__, 64, 'class'),
                player_module=_text(type(player).__module__, 128, 'module'),
                player_owner_id=id(player),
                player_is_original_avatar=type(player) is Avatar.PlayerAvatar,
                player_is_original_account=type(player) is Account.PlayerAccount,
                entity_id=_integer(player.id, 1, 2147483647, 'entityID'))
    missing = data['unavailable']
    data['name'] = _optional(player, 'name', 'name', lambda v, n: _text(v, 128, n), missing)
    if not data['player_is_original_avatar']:
        return data
    data['space_id'] = _optional(player, 'spaceID', 'spaceID',
                                lambda v, n: _integer(v, 0, 4294967295, n), missing,
                                none_is_unavailable=True)
    if data['space_id'] is None:
        # A base-only checkpoint has no native space. Do not sample spatial
        # getters or portray their unmeasured null as an actual native value.
        missing.append('position_without_space')
    else:
        data['position'] = _optional(player, 'position', 'position', _position, missing)
    data['in_world'] = _optional(player, 'inWorld', 'inWorld', _boolean, missing)
    data['steps_till_init'] = _optional(player, '_PlayerAvatar__stepsTillInit', 'steps_till_init',
                                      lambda v, n: _integer(v, 0, 4, n), missing)
    data['space_initialized'] = _optional(player, '_PlayerAvatar__isSpaceInitialized',
                                         'space_initialized', _boolean, missing)
    if data['steps_till_init'] is not None:
        data['user_sees_world'] = _boolean(player.userSeesWorld(), 'userSeesWorld')
        if data['user_sees_world'] != (data['steps_till_init'] == 0):
            raise ValueError('original readiness getter differs from its private counter')
    data['world_draw_enabled'] = _boolean(BigWorld.worldDrawEnabled(), 'worldDrawEnabled')
    if data['space_id'] is None:
        missing.append('space_load_without_space')
    else:
        data['space_load_progress'] = _number(BigWorld.spaceLoadStatus(), 0, 1, 'spaceLoadStatus')
    arena = getattr(player, 'arena', None)
    if arena is not None:
        if type(arena) is not ClientArena.ClientArena:
            raise ValueError('expected original ClientArena instance')
        data.update(arena_present=True,
                    arena_type_id=_integer(arena.arenaType.id, 0, 2147483647, 'arenaTypeID'),
                    arena_unique_id=_integer(arena.arenaUniqueID, 0, 18446744073709551615, 'arenaUniqueID'),
                    geometry_name=_text(arena.arenaType.geometryName, 64, 'geometryName'),
                    geometry_path=_text(arena.arenaType.geometry, 128, 'geometry'))
        if not isinstance(arena.vehicles, dict) or len(arena.vehicles) > 64:
            raise ValueError('bounded native arena vehicle list required')
        data['arena_vehicle_count'] = len(arena.vehicles)
    data['player_vehicle_id'] = _optional(player, 'playerVehicleID', 'playerVehicleID',
                                          lambda v, n: _integer(v, 0, 2147483647, n), missing)
    if data['player_vehicle_id']:
        vehicle = BigWorld.entity(data['player_vehicle_id'])
        data['vehicle_present'] = vehicle is not None
        if vehicle is not None:
            data['vehicle_is_original'] = type(vehicle) is Vehicle.Vehicle
            data['vehicle_in_world'] = _boolean(vehicle.inWorld, 'vehicle.inWorld')
            data['vehicle_descriptor_present'] = vehicle.typeDescriptor is not None
    return data


def observe(record):
    """Read only transient references; absence is explicit, never a ready flag."""
    global _observations
    if not _provenance_checked:
        raise RuntimeError('native original resource/source export required before observation')
    if _observations >= MAX_OBSERVATIONS:
        raise RuntimeError('arena observation budget exhausted')
    _observations += 1
    data = _collect_observation()
    data['observation_index'] = _observations
    return _emit(record, 'arena_entry_observation', data)
