# -*- coding: utf-8 -*-
"""Arena-only original #717 services, with two-phase native shutdown.

No Entity, geometry, GUI, world-draw flag, protocol or gameplay is synthesized.
Call fini_before_entities(), the existing native entity/space cleanup, and then
fini_after_entities(). A destroyed TriggersManager must remain addressable while
original Avatar.onLeaveWorld still calls its enable(False) method.
"""
import hashlib
import os
import types
import arena_entry_probe as bounds

VERSION = 1
SOURCE_HASHES = (
    ('res/scripts/client/helpers/DecalMap.pyc', '36429dc7155fd891096e8fad275fadada53b23e7fd18255b09f3f2b6be24d25d'),
    ('res/scripts/client/helpers/EdgeDetectColorController.pyc', '2f49ea763a7c0965425fbda255b2c678e5d293a5bf29e4aa47b612006873f8c7'),
    ('res/scripts/client/TriggersManager.pyc', '2e62259be7ffd0c6872660904696bcadb8b1d302d58e888af77c9e545982c376'),
    ('res/scripts_config.xml', 'f985ee2676a4c2f244f8ff5eae1c9321f24b21af0755b984e2ab940c89156349'),
    ('res/scripts/item_defs/vehicles/common/chassis_effects.xml', '0467d71232958716e0c54c1c8c9d01bab2841ddd19c9bb813c6b0d991a281687'),
    ('res/scripts/client/game.pyc', '2f2057748cbbbaefe21c5fd434cc1492bd08521f705f43832e45e493af6896c1'),
)
# Module key, class (None means module function), method attribute, co_name,
# original source line, positional argument count, original co_code SHA256.
METHODS = (
    ('decal', 'DecalMap', '__init__', '__init__', 17, 2, '101cd02beb1a31d5ab683f293e9f2e41b04e5fad8a4655371078c7ca06bda81e'),
    ('decal', 'DecalMap', '_readCfg', '_readCfg', 86, 2, 'ba7e0e7a3f8075707a7b5e5fe20422018bbfd59812f979da4976046d530401c7'),
    ('edge', 'EdgeDetectColorController', '__init__', '__init__', 13, 2, 'eb1aad1c9c88a010bf7154f597fde91d458a18cc50a38a5d505ac0f26a3438d6'),
    ('edge', 'EdgeDetectColorController', '_EdgeDetectColorController__readColors', '__readColors', 33, 4, 'c347789a190282376ee1d1b85e21824d1e7c55346690f994ef2f5f1830aaebac'),
    ('edge', 'EdgeDetectColorController', 'destroy', 'destroy', 29, 1, '74a17a71a2e6868625485f6c664ba2c2478cb555cbe32174c6c0d68bb8d17ee1'),
    ('triggers', None, 'init', 'init', 336, 0, '5e5a6d6b77f99c2cb3202220797788aff7e96be7ed72a2c39d7ac52369515cd5'),
    ('triggers', 'TriggersManager', '__init__', '__init__', 78, 1, '68b8b3755781413573342cad3a1246729a8d31d760316cdf892d25a07e713d68'),
    ('triggers', 'TriggersManager', 'destroy', 'destroy', 99, 1, 'fd7868130d9ca48396c700dff523c58c465a0bf69e5f8eeb101c77db4f9326a4'),
    ('triggers', 'TriggersManager', 'enable', 'enable', 116, 2, 'd8a4656ab379e39dc99b845bd25503063ba00be06b795c0d0a41bfa95e8cbcbc'),
)
FILENAMES = {'decal': 'scripts/client/helpers/DecalMap.py',
             'edge': 'scripts/client/helpers/EdgeDetectColorController.py',
             'triggers': 'scripts/client/TriggersManager.py'}
GROUPS = {'slow': (100.0, 10000.0), 'medium': (50.0, 5000.0), 'fast': (25.0, 2500.0)}
TEXTURES = {
    'explosion': 'maps/fx/decal_ground_1.dds', 'bumpExplosion': 'maps/fx/decal_ground_1_NM.dds',
    'explosionGround': 'maps/fx/decal_ground_1.dds', 'explosionGroundHE': 'maps/fx/decal_ground_1.dds',
    'bumpExplosionGround': 'maps/fx/decal_ground_1_NM.dds',
    'explosionSand': 'maps/fx/decal_sand_1.dds', 'explosionSandHE': 'maps/fx/decal_sand_1.dds',
    'bumpExplosionSand': 'maps/fx/decal_sand_1_NM.dds',
    'explosionSnow': 'maps/fx/decal_snow_1.dds', 'explosionSnowHE': 'maps/fx/decal_snow_1.dds',
    'bumpExplosionSnow': 'maps/fx/decal_snow_1_NM.dds',
    'explosionStone': 'maps/fx/decal_stone_1.dds', 'explosionStoneHE': 'maps/fx/decal_stone_1.dds',
    'bumpExplosionStone': 'maps/fx/decal_stone_1_NM.dds',
}
COLORS = {'common/self': (0.5, 0.5, 0.5, 1.0), 'common/enemy': (1.0, 0.070, 0.027, 1.0),
          'common/friend': (0.488, 0.839, 0.023, 1.0), 'colorBlind/self': (0.5, 0.5, 0.5, 1.0),
          'colorBlind/enemy': (0.511, 0.472, 0.992, 1.0), 'colorBlind/friend': (0.488, 0.839, 0.023, 1.0)}
_record = None
_context = None
_owned = {}
_attempted = False
_before = False
_after = False
_errors = []
_destroyed = set()


def _emit(phase, stage=None, **fields):
    data = {'version': VERSION, 'phase': phase, 'stage': stage}
    data.update(fields)
    return bounds._emit(_record, 'arena_bootstrap', data)


def _sources(root):
    if not os.path.isabs(root) or not os.path.isdir(root):
        raise ValueError('absolute prepared client cwd required')
    root = os.path.normcase(os.path.realpath(root))
    result = []
    for relative, expected in SOURCE_HASHES:
        path = os.path.join(root, *relative.split('/'))
        resolved = os.path.normcase(os.path.realpath(path))
        if (not resolved.startswith(root + os.sep) or os.path.islink(path)
                or not os.path.isfile(path) or not 1 <= os.path.getsize(path) <= bounds.MAX_SOURCE_BYTES):
            raise ValueError('bounded original arena bootstrap source required')
        with open(path, 'rb') as stream:
            raw = stream.read(bounds.MAX_SOURCE_BYTES + 1)
        if not 1 <= len(raw) <= bounds.MAX_SOURCE_BYTES or hashlib.sha256(raw).hexdigest() != expected:
            raise ValueError('arena bootstrap source/config hash mismatch: ' + relative)
        result.append({'relative_path': relative, 'bytes': len(raw), 'sha256': expected})
    return result


def _load_context():
    import Avatar
    import BigWorld
    import ResMgr
    import Settings
    import TriggersManager
    from helpers import DecalMap, EdgeDetectColorController
    if Settings.g_instance is None:
        raise RuntimeError('original Settings must already exist')
    return {'decal': DecalMap, 'edge': EdgeDetectColorController, 'triggers': TriggersManager,
            'script_config': Settings.g_instance.scriptConfig, 'resources': ResMgr,
            'engine': BigWorld, 'avatar_class': Avatar.PlayerAvatar}


def _bindings(context):
    for key, cls, attribute, name, line, count, digest in METHODS:
        target = context[key] if cls is None else getattr(context[key], cls)
        bounds._code_contract(getattr(target, attribute),
                              (attribute, name, line, count, digest), FILENAMES[key])


def _children(section, expected, label):
    if section is None:
        raise ValueError('original config section missing: ' + label)
    rows = section.items()
    if type(rows) not in (list, tuple) or len(rows) != len(expected):
        raise ValueError('original config child count differs: ' + label)
    result = {}
    for name, child in rows:
        name = bounds._text(name, 64, label)
        if name in result or name not in expected:
            raise ValueError('original config child names differ: ' + label)
        result[name] = child
    if set(result) != set(expected):
        raise ValueError('original config child set differs: ' + label)
    return result


def _config(context):
    config = context['script_config']
    decal, edge = config['decal'], config['silhouetteColors']
    parts = _children(decal, ('criticalAngle', 'groups', 'textures'), 'decal')
    angle = bounds._number(decal.readFloat('criticalAngle'), 0, 90, 'criticalAngle')
    if angle != 30.0:
        raise ValueError('original decal criticalAngle differs')
    groups = _children(parts['groups'], GROUPS, 'groups')
    group_values = {}
    for name in sorted(groups):
        _children(groups[name], ('lifeTime', 'trianglesCount'), 'group')
        pair = [bounds._number(groups[name].readFloat(field), 0, 100000, field)
                for field in ('lifeTime', 'trianglesCount')]
        if tuple(pair) != GROUPS[name]:
            raise ValueError('original decal group differs: ' + name)
        group_values[name] = pair
    textures = _children(parts['textures'], TEXTURES, 'textures')
    for name in sorted(textures):
        _children(textures[name], ('texture',), 'texture')
        if textures[name].readString('texture') != TEXTURES[name]:
            raise ValueError('original decal texture differs: ' + name)
    color_parts = _children(edge, ('common', 'colorBlind'), 'silhouetteColors')
    for section in color_parts.values():
        _children(section, ('self', 'enemy', 'friend'), 'silhouette colors')
    colors = {}
    for name, expected in COLORS.items():
        vector = edge.readVector4(name)
        actual = [bounds._number(getattr(vector, c), 0, 1, 'color') for c in ('x', 'y', 'z', 'w')]
        # ResMgr returns FLOAT32 vectors from decimal text. The tolerance only
        # accommodates that conversion; shape, keys and original bytes are pinned.
        if any(abs(a - e) > 0.000001 for a, e in zip(actual, expected)):
            raise ValueError('original silhouette color differs: ' + name)
        colors[name] = actual
    chassis = context['resources'].openSection('scripts/item_defs/vehicles/common/chassis_effects.xml/decals')
    if chassis is None or chassis['bufferPrefs'] is None or chassis['textureSets'] is None:
        raise ValueError('original chassis decal sections unavailable')
    return {'critical_angle': angle, 'groups': group_values, 'textures': dict(TEXTURES),
            'colors': colors, 'chassis_decals_present': True}, decal, edge


def _slot(key):
    return 'g_manager' if key == 'triggers' else 'g_instance'


def _exact_instance(instance, expected_class):
    # The three pinned #717 declarations have no bases and are old-style
    # ClassType objects on Python 2.7. Their instances have InstanceType, not
    # type(instance) == expected_class. Do not accept subclasses or a foreign
    # new-style object's spoofed __class__ property.
    if type(instance) is expected_class:
        return True
    old_class = getattr(types, 'ClassType', None)
    old_instance = getattr(types, 'InstanceType', None)
    return (old_class is not None and type(expected_class) is old_class and
            type(instance) is old_instance and instance.__class__ is expected_class)


def _assert_no_avatar(context):
    engine = context['engine']
    player = engine.player()
    if type(player) is context['avatar_class']:
        raise RuntimeError('cannot release arena services while native Avatar is player')
    values = engine.entities.values()
    if len(values) > 64 or any(type(entity) is context['avatar_class'] for entity in values):
        raise RuntimeError('native Avatar/entities must be cleared before service release')


def init(record):
    """Install only the three measured original services before player switch."""
    global _record, _context, _attempted
    if _attempted:
        raise RuntimeError('arena bootstrap initialization already attempted')
    if not callable(record):
        raise ValueError('diagnostic record function required')
    _attempted = True
    _record = record
    _context = _load_context()
    sources = _sources(os.getcwd())
    _bindings(_context)
    _assert_no_avatar(_context)
    for key in ('decal', 'edge', 'triggers'):
        if getattr(_context[key], _slot(key)) is not None:
            raise RuntimeError('arena bootstrap refuses an existing singleton: ' + key)
    config, decal, edge = _config(_context)
    _emit('provenance', sources=sources, method_count=len(METHODS), config=config)
    try:
        for key, argument in (('decal', decal), ('edge', edge), ('triggers', None)):
            _emit('init_begin', key)
            module = _context[key]
            if key == 'triggers':
                module.init()
                instance = module.g_manager
                expected_class = module.TriggersManager
            else:
                expected_class = module.DecalMap if key == 'decal' else module.EdgeDetectColorController
                instance = expected_class(argument)
                setattr(module, _slot(key), instance)
            # Store before any diagnostic operation so partial failures can
            # clean up the original instance already assigned by init().
            _owned[key] = instance
            if not _exact_instance(instance, expected_class):
                raise ValueError('original constructor returned an unexpected class')
            _emit('init_return', key, owner_id=id(instance),
                  class_model='python2_old_style' if type(instance) is getattr(types, 'InstanceType', None) else 'new_style',
                  instance_type=type(instance).__name__, expected_class=expected_class.__name__, exact_class=True)
    except Exception as exc:
        failures = []
        for function in (fini_before_entities, fini_after_entities):
            try:
                function()
            except Exception as cleanup_exc:
                failures.append(type(cleanup_exc).__name__)
        _emit('init_error', error_type=type(exc).__name__, cleanup_errors=failures)
        raise
    _emit('ready', stages=['decal', 'edge', 'triggers'], native_lifecycle_forced=False)


def fini_before_entities():
    """Original destroy order; retain TriggersManager for Avatar.onLeaveWorld."""
    global _before
    if _record is None or _before:
        return
    _before = True
    for key in ('triggers', 'edge'):
        if key not in _owned:
            continue
        try:
            _bindings(_context)
            instance = _owned[key]
            if getattr(_context[key], _slot(key)) is not instance:
                raise RuntimeError('owned arena singleton was replaced: ' + key)
            _emit('destroy_begin', key, owner_id=id(instance))
            instance.destroy()
            _destroyed.add(key)
            if key == 'edge':
                _context[key].g_instance = None
            _emit('destroy_return', key, owner_id=id(instance),
                  retained_for_native_leave=(key == 'triggers'))
        except Exception as exc:
            _errors.append(key + ':' + type(exc).__name__)
            _emit('destroy_error', key, error_type=type(exc).__name__)
    _emit('before_entities_complete', errors=list(_errors),
          triggers_retained=('triggers' in _owned))
    if _errors:
        raise RuntimeError('arena service destruction failed: ' + ', '.join(_errors))


def fini_after_entities():
    """Release only owned globals after real native entity/space teardown."""
    global _after, _context
    if _record is None or _after:
        return
    if not _before:
        raise RuntimeError('arena pre-entity shutdown must run first')
    if _owned:
        _assert_no_avatar(_context)
    for key in ('triggers', 'edge', 'decal'):
        if key not in _owned:
            continue
        try:
            current = getattr(_context[key], _slot(key))
            expected = None if key == 'edge' and key in _destroyed else _owned[key]
            if current is not expected:
                raise RuntimeError('refusing to overwrite a replaced arena singleton')
            setattr(_context[key], _slot(key), None)
            _emit('restore_return', key, restored_to_none=True,
                  native_entities_absent=True, original_destroy_exists=(key != 'decal'))
        except Exception as exc:
            _errors.append(key + ':restore:' + type(exc).__name__)
            _emit('restore_error', key, error_type=type(exc).__name__)
    _after = True
    _owned.clear()
    _context = None
    _emit('after_entities_complete', errors=list(_errors))
    if _errors:
        raise RuntimeError('arena cleanup/release failed: ' + ', '.join(_errors))
