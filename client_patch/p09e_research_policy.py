# -*- coding: utf-8 -*-
"""Explicit, reversible #717 UI policy: research costs zero XP in test_lab.

Call before original GUI personality initialization. Early resource init and an
already populated vehicles cache are supported; an already loaded tech tree is
rejected to avoid stale cached costs. Original conversion/validation runs first.
Only ordered unlock row XP values change. This is not server authorization.
"""
import hashlib
import sys

POLICY = 'test_lab.research.free-credit-xp.v1'
AUDITED_SOURCE = 'scripts/common/items/vehicles.py'
AUDITED_PYC_SHA256 = '805240e4b59d8a75950dbb97b41c17867606e7e96d7ff0c8d7b05312b83ae8b6'
CONVERTER_CODE_SHA256 = '89fb933bfc007c68d34a0871c88f85fbeabffba5f7f439641f1da48063207915'
METHOD = '_VehicleType__convertAndValidateUnlocksDescrs'
CACHE_FIELD = '_Cache__vehicles'
MAX_VEHICLES = 1024
MAX_UNLOCKS = 256
_guard = None

try:
    _INTEGER_TYPES = (int, long)
except NameError:
    _INTEGER_TYPES = (int,)


def _int(value, low, high):
    return type(value) in _INTEGER_TYPES and low <= value <= high


def zero_xp_rows(rows):
    """Return a new list with exact target/prerequisite tuple tails preserved."""
    if type(rows) is not list or len(rows) > MAX_UNLOCKS:
        raise ValueError('unexpected native unlock list')
    result = []
    for row in rows:
        if (type(row) is not tuple or not 2 <= len(row) <= MAX_UNLOCKS
                or not _int(row[0], 0, 2147483647)
                or not all(_int(value, 1, 0xffffff) for value in row[1:])):
            raise ValueError('unexpected native unlock tuple')
        result.append((0,) + row[1:])
    return result


def _audit_class(vehicle_class):
    original = vehicle_class.__dict__.get(METHOD)
    code = getattr(original, 'func_code', getattr(original, '__code__', None))
    expected_names = ('id', 'None', 'g_list', 'getIDsByName', 'nations', 'NAMES',
                      'g_cache', 'chassisIDs', 'turretIDs', 'gunIDs', 'engineIDs',
                      'fuelTankIDs', 'radioIDs', 'Exception', 'LOG_CURRENT_EXCEPTION',
                      'name', 'makeIntCompactDescrByID', 'installableComponents',
                      'setdefault', 'set', 'update', 'append', 'itervalues', 'tuple',
                      '_collectReqItemsRecursively', 'get', 'xrange', 'len')
    expected_consts = (None, 0, 1, 2, 'vehicle', ':', 'vehicleChassis',
                       'vehicleTurret', 'vehicleGun', 'vehicleEngine', 'vehicleFuelTank',
                       'vehicleRadio', "wrong name '%s' in <unlocks> of '%s'",
                       "component '%s' in <unlocks> is not for '%s'", 3, ())
    if (code is None or code.co_argcount != 2 or code.co_firstlineno != 1961
            or code.co_filename != AUDITED_SOURCE or code.co_names != expected_names
            or code.co_consts != expected_consts
            or hashlib.sha256(code.co_code).hexdigest() != CONVERTER_CODE_SHA256):
        raise ValueError('research cost policy requires exact audited #717 converter')
    return original


def _require_unloaded_tree(modules):
    for module_name, module in list(modules.items()):
        if module_name.lower().endswith('.techtree.techtree_dp'):
            provider = getattr(module, 'g_techTreeDP', None)
            # A known provider with the exact False state is safe. Unknown
            # provider/cache layouts fail closed before any descriptor changes.
            if provider is None or getattr(provider, '_TechTreeDataProvider__loaded', None) is not False:
                raise ValueError('research cost policy must precede loaded tech tree')


class _ResearchCostGuard(object):
    """Keep exact original row objects for an all-or-nothing owned rollback."""
    def __init__(self, vehicle_class, cache, record, original):
        if not callable(record) or vehicle_class.__dict__.get(METHOD) is not original:
            raise ValueError('research policy binding/recorder changed')
        self.vehicle_class = vehicle_class
        self.cache = cache
        self.record = record
        self.original = original
        self.rows = []
        self.active = False
        guard = self

        def convert(vehicle, source):
            if not guard.active:
                raise RuntimeError('research policy callback after restoration')
            rows = guard.original(vehicle, source)
            projected = zero_xp_rows(rows)
            guard._remember(vehicle, rows, projected)
            return projected

        self.replacement = convert

    def _remember(self, vehicle, rows, projected):
        if len(self.rows) >= MAX_VEHICLES or any(row[0] is vehicle for row in self.rows):
            raise ValueError('research policy vehicle bound/duplicate conversion')
        self.rows.append((vehicle, rows, projected))

    def install(self):
        if self.active or self.vehicle_class.__dict__.get(METHOD) is not self.original:
            raise RuntimeError('research policy already installed or binding changed')
        prepared = []
        if self.cache is not None:
            cached = getattr(self.cache, CACHE_FIELD, None)
            if type(cached) is not dict or len(cached) > MAX_VEHICLES:
                raise ValueError('unexpected original vehicle cache')
            for key, vehicle in list(cached.items()):
                if (type(key) is not tuple or len(key) != 2
                        or not _int(key[0], 0, 15) or not _int(key[1], 0, 255)
                        or not isinstance(vehicle, self.vehicle_class)
                        or getattr(vehicle, 'id', None) != key):
                    raise ValueError('unexpected cached vehicle identity')
                rows = vehicle.unlocksDescrs
                prepared.append((vehicle, rows, zero_xp_rows(rows)))
            if len(set(id(row[0]) for row in prepared)) != len(prepared):
                raise ValueError('duplicate cached vehicle identity')
        self.record('research_cost_policy', phase='install', policy=POLICY,
                    cached_vehicles=len(prepared), changed_field='unlocksDescrs[index][0]',
                    historical_graph_preserved=True, native_acceptance='NOT_RUN')
        self.rows = prepared
        setattr(self.vehicle_class, METHOD, self.replacement)
        for vehicle, original, projected in prepared:
            vehicle.unlocksDescrs = projected
        self.active = True

    def restore(self):
        if not self.active:
            return
        if self.vehicle_class.__dict__.get(METHOD) is not self.replacement:
            raise RuntimeError('research policy binding changed before rollback')
        # A constructor failing immediately after conversion may not have
        # assigned unlocksDescrs yet. It cannot be a successful cached vehicle.
        for vehicle, original, projected in self.rows:
            current = getattr(vehicle, 'unlocksDescrs', None)
            if current is not None and (current is not projected or current != zero_xp_rows(original)):
                raise RuntimeError('research descriptor changed before rollback')
        for vehicle, original, projected in self.rows:
            if getattr(vehicle, 'unlocksDescrs', None) is not None:
                vehicle.unlocksDescrs = original
        setattr(self.vehicle_class, METHOD, self.original)
        self.active = False
        self.record('research_cost_policy', phase='restore', policy=POLICY,
                    historical_costs_restored=True, restored_vehicles=len(self.rows))


def init(record, policy):
    """Explicit opt-in; before items.init or after it, but before GUI init."""
    global _guard
    if policy != POLICY:
        raise ValueError('explicit test_lab research policy required')
    if _guard is not None:
        raise RuntimeError('research policy initialized twice')
    _require_unloaded_tree(sys.modules)
    from items import vehicles
    original = _audit_class(vehicles.VehicleType)
    candidate = _ResearchCostGuard(vehicles.VehicleType, getattr(vehicles, 'g_cache', None), record, original)
    candidate.install()
    _guard = candidate


def fini():
    """Call after original GUI disposal; a future GUI must rebuild its tree."""
    global _guard
    if _guard is not None:
        _guard.restore()
        _guard = None
