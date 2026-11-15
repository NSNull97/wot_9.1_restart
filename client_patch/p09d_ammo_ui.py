# -*- coding: utf-8 -*-
"""Opt-in native #717 ammunition UI policy and bounded passive observations.

Original fillVehicle, inventory, Account and render handlers are not replaced.
The server owns counts and authorization. The module-install reload may use
the original layout processor with the gun's defaults on a zero-price shop.
"""
import hashlib
import importlib
import crew_vehicles

try:
    _INTEGER = (int, long)
except NameError:
    _INTEGER = (int,)

MOUNTS = {
    3329: (5891, 5892, 96, (2570, 2826, 3082)),
    7169: (12035, 14852, 30, (14602, 14858, 15114)),
}
SOURCE = 'scripts/client/gui/Scaleform/daapi/view/lobby/hangar/TechnicalMaintenance.py'
NOTICE = u'Ремонт и автоматическое обслуживание пока недоступны.'
MAX_EVENTS = 4096
# Shell types are shared across the garage: the verified 0.9.1 inventory has
# 569 types. This is independent of the 256-owned-vehicle bound.
MAX_SHELL_DEPOT_TYPES = 1024
_binding = None
_record = None
_events = 0
_truncated = False
_observer_disabled = False
_default_reload = None

_RELOAD_NAME = 'tryToLoadDefaultShellsLayout'
_RELOAD_MODULE = 'gui.shared.gui_items.processors.vehicle'
_RELOAD_CALLERS = ('gui.shared.gui_items.processors.module',
    'gui.Scaleform.daapi.view.lobby.hangar.AmmunitionPanel',
    'gui.Scaleform.daapi.view.lobby.techtree.Research')
_ADISP_SOURCE = 'scripts/common/adisp.py'

# Exact original code records, not replacement wrappers or inferred success.
TARGETS = {
    ('scripts/client/Account.py', 'update'): (693, 'db3bfd5161ec8f571682c575ae5ddd1bc65f3e8dee3a5142dc8333c4a4700c93'),
    ('scripts/client/Account.py', '_update'): (1451, 'dae41b7ea6209f0983a647174802481619919ee942282786430a5a7b3c7cf0ce'),
    ('scripts/client/Account.py', 'onCmdResponseExt'): (302, '37edde4729913fbb2b7fb9bc1069259ac54a9416218061eaca5166e6cb8aec48'),
    ('scripts/client/account_helpers/Inventory.py', 'synchronize'): (68, '2be8281a523c38f925ee35c6da61992abbd6e4753815f6f32539206bde6bcde1'),
    ('scripts/client/account_helpers/Inventory.py', '__setAndFillLayouts_onShopSynced'): (794, '12eac125934455e917f71ac0e2c80dd0043f5807bf25c89d7004dfd0fdb16039'),
    (SOURCE, '_populate'): (43, '4d0db960297e83f286cb4a9bf47cac423ddde25491fef441b4be7f6b71b0f3e7'),
    (SOURCE, 'fillVehicle'): (317, '985576363cbe8797ff736de480b5b8305f318f3da37a702514ace6d4bf4443c8'),
    (SOURCE, '__setVehicleLayouts'): (429, '14cd36b3c4195280f36a3e2a5061505b37f990f079103f32783b3a63707b4a0a'),
    ('scripts/client/gui/Scaleform/daapi/view/meta/TechnicalMaintenanceMeta.py', 'as_setDataS'): (73, 'a07a7ee689046d4e29fdf9eec47a9e62036dd61fc57ba9dd88615e7fbac06313'),
    ('scripts/client/gui/shared/gui_items/processors/vehicle.py', '_request'): (391, 'db78dcf6887f4980ac6a0b75621aaea228702d5e30b1615c9004d1ede5d9d152'),
    ('scripts/client/gui/shared/gui_items/processors/vehicle.py', '_successHandler'): (401, '645b3b51989f64c06107cbc6f3dfa0f8aa8340be0eb140eba2abf5bccba86cc4'),
    ('scripts/client/gui/shared/gui_items/processors/vehicle.py', '_errorHandler'): (447, 'aecc595c8c612a570b36c1291a82167b59ae1bc91ea314c94fe1d7e45703c6d5'),
}


def _integer(value, minimum=0, maximum=2147483647):
    if type(value) not in _INTEGER or not minimum <= value <= maximum:
        raise ValueError('native ammunition integer bound')
    return value


def _mapping(value, maximum=32):
    if type(value) is not dict or len(value) > maximum:
        raise ValueError('native ammunition dictionary bound')
    return value


def flat(value, signed=False):
    # SPG-02: a CAT-01 gun has one to three shells, so one to three pairs.
    if type(value) not in (tuple, list) or len(value) not in (2, 4, 6):
        raise ValueError('native ammunition requires one to three pairs')
    result = []
    for index in range(0, len(value), 2):
        identity = _integer(value[index], -65535 if signed else 1, 65535)
        if identity == 0:
            raise ValueError('zero shell identity')
        result.extend((identity, _integer(value[index + 1], 0, 1000000)))
    if len(set(abs(result[index]) for index in range(0, len(result), 2))) != len(result) // 2:
        raise ValueError('duplicate shell identity')
    return result


def mounted(item):
    """Read the actual selected native descriptor, never authorize a command."""
    identity = _integer(item.intCD, 1, 65535)
    mounts = crew_vehicles.mounts(MOUNTS)  # CREW-ANY: every CAT-01 stock mount
    if identity not in mounts:
        return None
    turret, gun, capacity, shells = mounts[identity]
    desc = item.descriptor
    if crew_vehicles.enabled() and (desc.turret['compactDescr'], desc.gun['compactDescr']) != (turret, gun):
        # CONTENT-0 4: another turret x gun pair of a catalogue vehicle; the mount is the descriptor's own gun
        # (capacity and shots), and the server authorizes every command against the owned pair.
        turret, gun = desc.turret['compactDescr'], desc.gun['compactDescr']
        capacity = desc.gun['maxAmmo']
        shells = tuple(shot['shell']['compactDescr'] for shot in desc.gun['shots'])
    if (desc.type.compactDescr != identity or desc.turret['compactDescr'] != turret
            or desc.gun['compactDescr'] != gun or desc.gun['maxAmmo'] != capacity
            or item.ammoMaxSize != capacity or tuple(item.shellsLayoutIdx) != (turret, gun)):
        return None
    shots = desc.gun['shots']
    if (type(shots) not in (tuple, list) or not 1 <= len(shots) <= 3 or len(shells) != len(shots)
            or tuple(shot['shell']['compactDescr'] for shot in shots) != shells):
        return None
    return {'vehicle_type_cd': identity, 'inventory_id': _integer(item.invID, 1),
            'turret_cd': turret, 'gun_cd': gun, 'capacity': capacity,
            'compatible_shells': list(shells)}


def selection():
    from CurrentVehicle import g_currentVehicle
    from gui.shared import g_itemsCache
    if not g_itemsCache.isSynced() or not g_currentVehicle.isPresent():
        return None
    return mounted(g_currentVehicle.item)


def _zero_price_default_layout(vehicle, prices):
    mount = mounted(vehicle)
    if mount is None or not all(prices.get(cd) == (0, 0) for cd in mount['compatible_shells']):
        return None
    shells = tuple(vehicle.shells)
    if not any(shell.defaultCount > shell.inventoryCount for shell in shells):
        return None
    layout = flat([value for shell in shells for value in shell.defaultLayoutValue], signed=True)
    if ([abs(cd) for cd in layout[::2]] != mount['compatible_shells'] or sum(layout[1::2]) > mount['capacity']):
        raise RuntimeError('native default ammunition layout mismatch')
    return layout


def _verify_reload_code(function, source, line, digest):
    code = getattr(function, 'func_code', getattr(function, '__code__', None))
    if (code is None or code.co_filename != source or code.co_firstlineno != line
            or hashlib.sha256(code.co_code).hexdigest() != digest):
        raise RuntimeError('native #717 module ammunition reload source mismatch')


class _DefaultReload(object):
    def __init__(self, original, owners, processor, process, read_prices):
        self.original, self.owners = original, tuple(owners)
        self.installed = []

        def replacement(vehicle):
            layout = _zero_price_default_layout(vehicle, read_prices())
            if layout is None:
                return original(vehicle)

            def start(callback):
                @process
                def request():
                    result = yield processor(vehicle, layout).request()
                    callback(bool(result and result.success))
                request()

            return start

        self.replacement = replacement

    def install(self):
        if any(getattr(owner, _RELOAD_NAME, None) is not self.original for owner in self.owners):
            raise RuntimeError('native #717 module ammunition reload aliases changed')
        for owner in self.owners:
            setattr(owner, _RELOAD_NAME, self.replacement)
            self.installed.append(owner)

    def restore(self):
        if any(getattr(owner, _RELOAD_NAME, None) is not self.replacement for owner in self.installed):
            raise RuntimeError('foreign module ammunition reload replacement')
        for owner in reversed(self.installed):
            setattr(owner, _RELOAD_NAME, self.original)
        self.installed = []


def _setup_default_reload():
    from adisp import process
    from gui.shared import g_itemsCache

    vehicle = importlib.import_module(_RELOAD_MODULE)
    original = getattr(vehicle, _RELOAD_NAME)
    _verify_reload_code(original, _ADISP_SOURCE, 143, 'f7281c5fd24324e9279e9015fad7decb0936e16f631ff76664a6071df8b7391b')
    closure = getattr(original, 'func_closure', getattr(original, '__closure__', None))
    if closure is None or len(closure) != 3 or closure[0].cell_contents != 'callback':
        raise RuntimeError('native #717 module ammunition reload wrapper mismatch')
    wrapper = closure[2].cell_contents
    _verify_reload_code(wrapper, _ADISP_SOURCE, 138, '3814ec7ed28deee153a088aa3def670d9cbce6ecc2bdd286e85165a2f3c9f701')
    closure = getattr(wrapper, 'func_closure', getattr(wrapper, '__closure__', None))
    if closure is None or len(closure) != 2:
        raise RuntimeError('native #717 module ammunition reload wrapper mismatch')
    _verify_reload_code(closure[0].cell_contents, 'scripts/client/gui/shared/gui_items/processors/vehicle.py', 556,
                        '72c7ff76d9b9e0faa48e142d276b821aaa0eb2ab615fdc25ac8a7ec5a9fff716')
    owners = [importlib.import_module(name) for name in _RELOAD_CALLERS] + [vehicle]
    return _DefaultReload(original, owners, vehicle.VehicleLayoutProcessor, process,
                          lambda: g_itemsCache.items.shop.getPrices() if g_itemsCache.isSynced() else {})


def observe():
    """Actual selected native raw cache plus GUI projection; no mutation."""
    from CurrentVehicle import g_currentVehicle
    from gui.shared import g_itemsCache
    mount = selection()
    if mount is None:
        return {'supported': False}
    item = g_currentVehicle.item
    inv = _mapping(g_itemsCache.items.inventory.getCacheValue(1, {}), 32)
    owned = crew_vehicles.owned_bound(16)
    loaded_raw = _mapping(inv.get('shells', {}), owned).get(item.invID, [])
    loaded = [] if loaded_raw == [] else flat(loaded_raw)
    layouts = _mapping(_mapping(inv.get('shellsLayout', {}), owned).get(item.invID, {}), 8)
    layout = layouts.get((mount['turret_cd'], mount['gun_cd']))
    layout = None if layout is None else flat(layout, signed=True)
    depot = _mapping(g_itemsCache.items.inventory.getCacheValue(10, {}), MAX_SHELL_DEPOT_TYPES)
    shell_items = item.shells
    if type(shell_items) not in (tuple, list) or len(shell_items) != len(mount['compatible_shells']):
        raise ValueError('native GUI shell collection differs from the mount')
    gui = []
    for shell in shell_items:
        gui.append({'shell_cd': _integer(shell.intCD, 1, 65535),
                    'count': _integer(shell.count, 0, mount['capacity']),
                    'default_count': _integer(shell.defaultCount, 0, mount['capacity']),
                    'inventory_count': _integer(shell.inventoryCount, 0, 1000000)})
    if set(row['shell_cd'] for row in gui) != set(mount['compatible_shells']):
        raise ValueError('native GUI incompatible shell')
    for pairs in (loaded, layout or []):
        if pairs and set(abs(pairs[index]) for index in range(0, len(pairs), 2)) != set(mount['compatible_shells']):
            raise ValueError('native raw incompatible shell')
    before = mount
    if mounted(g_currentVehicle.item) != before or g_currentVehicle.item is not item:
        raise RuntimeError('native vehicle changed during observation')
    return {'supported': True, 'mount': mount, 'loaded': loaded, 'layout': layout,
            'depot': [[identity, _integer(depot.get(identity, 0), 0, 1000000)]
                      for identity in mount['compatible_shells']], 'gui_shells': gui}


class _Bindings(object):
    def __init__(self, cls, messages, gate_owner, record, read_selection):
        self.cls, self.messages, self.gate_owner = cls, messages, gate_owner
        self.record, self.read_selection = record, read_selection
        self.originals = dict((name, cls.__dict__[name]) for name in ('repair', 'setRefillSettings'))
        self.installed = []
        self.active = False
        self.gate_installed = False
        binding = self

        def repair(view):
            binding.deny('repair')

        def settings(view, intCD, repair, load, equip):
            binding.deny('automatic_service')

        def gate():
            if not binding.active:
                raise RuntimeError('ammunition gate used after cleanup')
            value = binding.read_selection()
            if value is None:
                return False
            binding.notice()
            binding.record('p09d_maintenance_entry', mount=value, original_callback_called=True,
                           funding='server_policy', server_authority=True)
            return True

        self.gate = gate
        self.replacements = (('repair', repair), ('setRefillSettings', settings))

    def notice(self):
        if self.messages.g_instance is None:
            raise RuntimeError('native messages unavailable')
        self.messages.pushMessage(NOTICE, type=self.messages.SM_TYPE.Warning)

    def deny(self, action):
        if not self.active:
            raise RuntimeError('ammunition policy used after cleanup')
        self.notice()
        self.record('p09d_service_denied', action=action, native_mutation_called=False)

    def install(self):
        if self.active or self.installed:
            raise RuntimeError('ammunition policy installed twice')
        for name, original in self.originals.items():
            if self.cls.__dict__.get(name) is not original:
                raise RuntimeError('maintenance binding changed before installation')
        for name, replacement in self.replacements:
            setattr(self.cls, name, replacement)
            self.installed.append((name, replacement))
        self.active = True
        self.gate_owner.set_maintenance_gate(self.gate)
        self.gate_installed = True

    def restore(self):
        for name, replacement in self.installed:
            if self.cls.__dict__.get(name) is not replacement:
                raise RuntimeError('refusing to overwrite foreign maintenance binding')
        if self.gate_installed:
            self.gate_owner.clear_maintenance_gate(self.gate)
            self.gate_installed = False
        for name, _ in reversed(self.installed):
            setattr(self.cls, name, self.originals[name])
        self.installed = []
        self.active = False


def _audit_class(cls):
    for name in ('_populate', 'fillVehicle'):
        function = cls.__dict__[name]
        code = getattr(function, 'func_code', getattr(function, '__code__', None))
        line, digest = TARGETS[(SOURCE, name)]
        if (code is None or code.co_filename != SOURCE or code.co_firstlineno != line
                or hashlib.sha256(code.co_code).hexdigest() != digest):
            raise RuntimeError('original maintenance source mismatch: ' + name)


class _LifecycleError(RuntimeError):
    def __init__(self, errors):
        self.errors = tuple(errors)
        RuntimeError.__init__(self, 'ammunition install/cleanup failed: ' + '; '.join(
            type(error).__name__ + ': ' + str(error) for error in errors))


def init(record, enabled=False, module_reload=False):
    global _binding, _record, _events, _truncated, _observer_disabled, _default_reload
    if enabled is not True:
        raise ValueError('explicit isolated ammunition service enable required')
    if _binding is not None or not callable(record):
        raise RuntimeError('ammunition policy initialized twice or recorder unavailable')
    from gui.Scaleform.daapi.view.lobby.hangar.TechnicalMaintenance import TechnicalMaintenance
    from gui import SystemMessages
    import hangar_capabilities
    _audit_class(TechnicalMaintenance)
    _record, _events, _truncated, _observer_disabled = record, 0, False, False
    _binding = _Bindings(TechnicalMaintenance, SystemMessages, hangar_capabilities, record, selection)
    try:
        _binding.install()
        if module_reload:
            _default_reload = _setup_default_reload()
            _default_reload.install()
        record('p09d_ui_policy', phase='install', original_fill_vehicle_preserved=True,
               no_client_command_generation=not module_reload, zero_price_module_reload=bool(module_reload), event_limit=MAX_EVENTS)
    except Exception as error:
        # Keep binding for explicit cleanup if installation/cleanup itself fails.
        try:
            fini()
        except Exception as cleanup_error:
            raise _LifecycleError((error, cleanup_error))
        raise


def fini():
    global _binding, _record, _default_reload
    if _default_reload is not None:
        _default_reload.restore()
        _default_reload = None
    if _binding is not None:
        _binding.restore()
        if _record is not None:
            _record('p09d_ui_policy', phase='restore', original_bindings_restored=True)
        _binding = None
    _record = None


def observe_profile(frame, phase):
    """Isolate diagnostic failure from the active profiler and game callbacks."""
    global _observer_disabled
    if _observer_disabled or _binding is None or not _binding.active or _record is None:
        return
    try:
        _observe_profile(frame, phase)
    except Exception as error:
        # A diagnostic snapshot or source-pin error must not escape sys.setprofile:
        # that would disable every profile hook, including unrelated diagnostics.
        # Keep the UI policy installed; mark this observer incomplete and stop it.
        _observer_disabled = True
        known = ('native ammunition dictionary bound', 'native ammunition observer source mismatch')
        message = str(error)
        code = getattr(frame, 'f_code', None)
        _record('p09d_trace_error', error_type=type(error).__name__,
                reason=message if message in known else 'unclassified',
                method=getattr(code, 'co_name', None), phase=phase,
                observer_disabled=True, native_acceptance_complete=False)


def _observe_profile(frame, phase):
    """Collect bounded observations; only observe_profile handles failures."""
    global _events, _truncated
    if _binding is None or not _binding.active or _record is None:
        return
    if phase not in ('call', 'return'):
        return
    code = frame.f_code
    pin = TARGETS.get((code.co_filename, code.co_name))
    if pin is None or code.co_firstlineno != pin[0]:
        return
    if _events >= MAX_EVENTS:
        if not _truncated:
            _truncated = True
            _record('p09d_trace_truncated', limit=MAX_EVENTS, native_acceptance_complete=False)
        return
    if hashlib.sha256(code.co_code).hexdigest() != pin[1]:
        raise RuntimeError('native ammunition observer source mismatch')
    values = frame.f_locals
    fields = {'source': code.co_filename, 'method': code.co_name, 'source_line': pin[0],
              'offset': frame.f_lasti, 'phase': phase, 'owner_id': id(values.get('self'))}
    for name in ('requestID', 'resultID', 'vehInvID', 'shopRev', 'code'):
        if name in values:
            fields[name] = _integer(values[name], -2147483648)
    for name in ('needRepair', 'needAmmo', 'needEquipment', 'isUnload', 'isOrderChanged', 'triggerEvents', 'isFullSync'):
        if name in values:
            if type(values[name]) is not bool:
                raise ValueError('native ammunition flag type')
            fields[name] = values[name]
    if code.co_name in ('_update', 'synchronize'):
        diff = _mapping(values.get('diff'), 64)
        fields['revision'] = _integer(diff.get('rev', 0))
        fields['previous_revision'] = _integer(diff.get('prevRev', 0))
        fields['has_inventory'] = 'inventory' in diff
    if code.co_name == 'as_setDataS':
        data = _mapping(values.get('data'))
        fields['capacity'] = _integer(data.get('maxAmmo', 0), 0, 10000)
        rows = data.get('shells', [])
        if type(rows) is not list or len(rows) > 3:
            raise ValueError('maintenance render shell bound')
        fields['shells'] = [dict((name, _integer(_mapping(row).get(name, 0), 0, 1000000))
            for name in ('compactDescr', 'count', 'userCount', 'inventoryCount')) for row in rows]
        fields['flash_bound'] = getattr(values.get('self'), 'flashObject', None) is not None
    if code.co_name == '__setAndFillLayouts_onShopSynced' and phase == 'return':
        arr = values.get('arr')
        if arr is not None:
            if type(arr) is not list or len(arr) > 16:
                raise ValueError('native layout request bound')
            fields['arguments'] = [_integer(value, -2147483648) for value in arr]
    if code.co_name == '_update' and phase == 'return':
        fields['snapshot'] = observe()
    _events += 1
    _record('p09d_native_ammo_call', **fields)
