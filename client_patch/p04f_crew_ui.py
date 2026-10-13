# -*- coding: utf-8 -*-
"""Narrow original #717 crew-transfer callbacks and opt-in native diagnostics.

No account, processor, inventory writer or response callback is replaced.
All assignments read below come from the original synchronized items cache.
"""
import copy
import hashlib
import math
import os
import re
import time
import p04d_crew_ui as recruitment
import p09d_ammo_ui as ammunition

VERSION = 1
POLICY = 'test_lab.ms1.existing_crew.assignment.v1'
NOTICE = u'Пересадка: только свои командир и механик-водитель МС-1. Остальные операции пока недоступны.'
COMMANDER_SHA256 = '926254dfdbc7acf5a5d0c163d57642c24105da3ab21a7255236060e9534b70b5'
TARGETS = (('Crew', 'equipTankman', False), ('Crew', 'unloadTankman', False),
           ('Crew', 'unloadAllTankman', False), ('Crew', 'unloadCrew', True),
           ('Barracks', 'unloadTankman', False))
STEPS = (('unload_driver', 'unloadTankman', (3,), 1, -1),
         ('seat_original_driver', 'equipTankman', (2, 1), 1, 2),
         ('replace_driver', 'equipTankman', (3, 1), 1, 3),
         ('unload_commander', 'unloadTankman', (1,), 0, -1),
         ('seat_commander', 'equipTankman', (1, 0), 0, 1),
         ('unload_whole_crew', 'unloadAllTankman', (), -1, -1),
         ('reseat_commander', 'equipTankman', (1, 0), 0, 1))
_guard = None
_scenario = None


def integer(value, low, high):
    return recruitment._integer(value, low, high)


def callback_integer(value, low, high):
    # Preserve finite integral Flash Number and canonical decimal ID arguments.
    if type(value) in recruitment.integer_types + (float,):
        if not low <= value <= high or int(value) != value:
            raise ValueError('unsupported transfer callback integer')
        return int(value)
    if isinstance(value, recruitment.string_types) and re.match(r'\A[0-3]\Z', value):
        return integer(int(value), low, high)
    raise ValueError('unsupported transfer callback argument')


def checked_expected(value):
    fields = set(('database_id', 'selected_inventory_id', 'free_quota', 'credits', 'gold', 'ms1_crew', 'tankmen'))
    row_fields = set(('inventory_id', 'vehicle_inventory_id', 'slot', 'sha256', 'nation_id',
                      'vehicle_type_id', 'role', 'role_level', 'no_skills', 'free_xp'))
    if type(value) is not dict or set(value) != fields:
        raise ValueError('exact native transfer snapshot required')
    integer(value['database_id'], 1, 2147483647)
    integer(value['selected_inventory_id'], 1, 1)
    integer(value['free_quota'], 0, 1)
    for key in ('credits', 'gold'):
        integer(value[key], 0, 9223372036854775807)
    crew, members = value['ms1_crew'], value['tankmen']
    if (type(crew) is not list or len(crew) != 2 or type(members) is not list
            or len(members) != 3 - value['free_quota']):
        raise ValueError('bounded owned native crew shape required')
    expected_ids = list(range(1, len(members) + 1))
    ids = []
    for row in members:
        if type(row) is not dict or set(row) != row_fields:
            raise ValueError('exact native crew member fields required')
        identity = integer(row['inventory_id'], 1, 3)
        ids.append(identity)
        for key, expected in (('nation_id', 0), ('vehicle_type_id', 13), ('role_level', 100), ('free_xp', 0)):
            integer(row[key], expected, expected)
        role = 'commander' if identity == 1 else 'driver'
        pin = COMMANDER_SHA256 if identity == 1 else recruitment.DRIVER_SHA256
        if row['role'] != role or row['sha256'] != pin or row['no_skills'] is not True:
            raise ValueError('source-bound native identity/passport differs')
        integer(row['vehicle_inventory_id'], -1, 1)
        integer(row['slot'], -1, 1)
        if identity in crew:
            seat = crew.index(identity)
            if (crew.count(identity) != 1 or row['vehicle_inventory_id'] != 1 or row['slot'] != seat
                    or role != ('commander', 'driver')[seat]):
                raise ValueError('duplicate or incompatible native assignment')
        elif row['vehicle_inventory_id'] != -1 or row['slot'] != -1:
            raise ValueError('unassigned native tankman must remain in barracks')
    if ids != expected_ids:
        raise ValueError('only the existing source-bound native identities are supported')
    for identity in crew:
        if identity is not None:
            integer(identity, 1, 3)
            if identity not in ids:
                raise ValueError('native crew references unowned identity')
    return copy.deepcopy(value)


def native_snapshot():
    return checked_expected(recruitment.native_snapshot())


def native_ammunition():
    """Bounded raw original caches for both vehicles, without selecting the IS-7."""
    from gui.shared import g_itemsCache
    if not g_itemsCache.isSynced():
        raise RuntimeError('synced ammunition cache required')
    inv = ammunition._mapping(g_itemsCache.items.inventory.getCacheValue(1, {}), 32)
    shells = ammunition._mapping(inv.get('shells', {}), 16)
    layouts = ammunition._mapping(inv.get('shellsLayout', {}), 16)
    vehicles = []
    for identity, type_cd in ((1, 3329), (2, 7169)):
        item = g_itemsCache.items.getVehicle(identity)
        if item is None or item.intCD != type_cd or ammunition.mounted(item) is None:
            raise RuntimeError('source-bound native ammunition mount required')
        loaded = shells.get(identity, [])
        loaded = [] if loaded == [] else ammunition.flat(loaded)
        row = ammunition._mapping(layouts.get(identity, {}), 8)
        values = []
        for mount, counts in sorted(row.items()):
            if type(mount) is not tuple or len(mount) != 2:
                raise ValueError('native ammunition layout key differs')
            values.append([integer(mount[0], 1, 65535), integer(mount[1], 1, 65535),
                           ammunition.flat(counts, signed=True)])
        vehicles.append(dict(inventory_id=identity, loaded=loaded, layouts=values))
    depot = ammunition._mapping(g_itemsCache.items.inventory.getCacheValue(10, {}), 64)
    return dict(vehicles=vehicles, depot=[[integer(key, 1, 65535), integer(value, 0, 1000000)]
                                        for key, value in sorted(depot.items())])


def projected_transfer(before, slot, identity):
    """Expected diagnostic value only; never writes the native items cache."""
    value = checked_expected(before)
    integer(slot, -1, 1)
    integer(identity, -1, 3)
    if slot == -1:
        if identity != -1:
            raise ValueError('whole crew unload requires sentinel')
        value['ms1_crew'] = [None, None]
    else:
        if identity == 0 or identity != -1 and identity not in [m['inventory_id'] for m in value['tankmen']]:
            raise ValueError('existing native identity required')
        value['ms1_crew'][slot] = None if identity == -1 else identity
    for member in value['tankmen']:
        if member['inventory_id'] in value['ms1_crew']:
            member['vehicle_inventory_id'] = 1
            member['slot'] = value['ms1_crew'].index(member['inventory_id'])
        else:
            member['vehicle_inventory_id'], member['slot'] = -1, -1
    return checked_expected(value)


class _TransferGuard(object):
    def __init__(self, classes, messages, record, snapshot=None):
        if set(classes) != set(('Crew', 'Barracks')) or not callable(record):
            raise ValueError('audited original transfer classes and recorder required')
        self.record, self.messages = record, messages
        self.snapshot = native_snapshot if snapshot is None else snapshot
        self.active, self.events, self.bindings = False, 0, []
        for class_name, name, static in TARGETS:
            cls, callback = classes[class_name], class_name + '.' + name
            original = cls.__dict__[name]
            if isinstance(original, staticmethod) != static:
                raise TypeError('unexpected native transfer descriptor')
            function = original.__get__(None, cls) if static else original
            if not callable(function):
                raise TypeError('native transfer callback required')
            replacement = self._wrapper(function, callback, name, static)
            self.bindings.append((cls, name, original, staticmethod(replacement) if static else replacement))

    def emit(self, event, **fields):
        if self.events >= 1024 and not event == 'p04f_transfer_policy':
            raise RuntimeError('crew transfer event budget exhausted')
        self.events += 1
        fields.update(version=VERSION, policy=POLICY)
        self.record(event, **fields)

    def _deny(self, callback):
        self.emit('p04f_transfer_denied', callback=callback, original_callback_called=False)
        if self.messages.g_instance is None:
            raise RuntimeError('original SystemMessages unavailable')
        self.messages.pushMessage(NOTICE, type=self.messages.SM_TYPE.Warning)

    def _wrapper(self, original, callback, name, static):
        guard = self
        def wrapped(*args, **kwargs):
            if not guard.active:
                raise RuntimeError('crew transfer callback after cleanup')
            supplied = args if static else args[1:]
            try:
                if kwargs or not static and not args:
                    raise ValueError('original positional transfer callback required')
                state = checked_expected(guard.snapshot())
                if name == 'equipTankman':
                    if len(supplied) != 2:
                        raise ValueError('equip callback arity')
                    identity, slot = callback_integer(supplied[0], 1, 3), callback_integer(supplied[1], 0, 1)
                    projected_transfer(state, slot, identity)
                    member = next(row for row in state['tankmen'] if row['inventory_id'] == identity)
                    if member['vehicle_inventory_id'] != -1:
                        raise ValueError('only owned barracks tankmen may be seated')
                elif name == 'unloadTankman':
                    if len(supplied) != 1:
                        raise ValueError('unload callback arity')
                    supplied_id = callback_integer(supplied[0], 1, 3)
                    if supplied_id not in state['ms1_crew']:
                        raise ValueError('tankman is not assigned to selected MS-1')
                    slot, identity = state['ms1_crew'].index(supplied_id), -1
                else:
                    if supplied or all(value is None for value in state['ms1_crew']):
                        raise ValueError('whole unload requires an occupied MS-1 and no arguments')
                    slot, identity = -1, -1
            except (ValueError, StopIteration):
                return guard._deny(callback)
            guard.emit('p04f_transfer_ui_call', callback=callback, vehicle=1, slot=slot, tankman_id=identity,
                       native_cmd=105, original_callback_called=True)
            return original(*args, **kwargs)
        return wrapped

    def install(self):
        if self.active:
            raise RuntimeError('crew transfer policy installed twice')
        for cls, name, original, replacement in self.bindings:
            if cls.__dict__.get(name) is not original:
                raise RuntimeError('native transfer binding changed before install')
        self.emit('p04f_transfer_policy', phase='install', other_crew_operations=False,
                  original_processors_preserved=True, original_inventory_preserved=True)
        for cls, name, original, replacement in self.bindings:
            setattr(cls, name, replacement)
        self.active = True

    def restore(self):
        if not self.active:
            return
        for cls, name, original, replacement in self.bindings:
            if cls.__dict__.get(name) is not replacement:
                raise RuntimeError('native transfer binding changed during cleanup')
        for cls, name, original, replacement in self.bindings:
            setattr(cls, name, original)
        self.active = False
        self.emit('p04f_transfer_policy', phase='restore', exact_original_bindings_restored=True)


def init(record):
    global _guard
    import crew_capabilities
    from gui.Scaleform.daapi.view.lobby.hangar.Crew import Crew
    from gui.Scaleform.daapi.view.lobby.barracks.Barracks import Barracks
    from gui import SystemMessages
    capability = crew_capabilities._guard
    if (_guard is not None or capability is None or not capability.active
            or capability.allow_transfer is not True):
        raise RuntimeError('explicit active transfer capability required')
    classes = dict(Crew=Crew, Barracks=Barracks)
    if any((row[0], row[1]) in [(classes[a], b) for a, b, _ in TARGETS] for row in capability.bindings):
        raise RuntimeError('transfer callbacks still restricted by crew capability policy')
    candidate = _TransferGuard(classes, SystemMessages, record)
    candidate.install()
    _guard = candidate


def fini():
    global _guard, _scenario
    if _guard is not None:
        _guard.restore()
        _guard = None
    _scenario = None


def observe_profile(frame, phase):
    """Observe only verified original Account.__doCmd return; never call it."""
    code, values = frame.f_code, frame.f_locals
    if (phase != 'return' or code.co_filename != 'scripts/client/Account.py'
            or code.co_name != '__doCmd' or values.get('cmd') != 105):
        return
    if (code.co_firstlineno != 1523 or hashlib.sha256(code.co_code).hexdigest()
            != 'efb40e1d1742e98179a41a6d907f06ec749d64f1e6419c414fe702535f42ec36'):
        raise RuntimeError('native transfer Account command source differs')
    if _guard is None or not _guard.active:
        raise RuntimeError('native transfer observation requires active policy')
    args = values.get('args')
    if type(args) is not tuple or len(args) != 3:
        raise ValueError('native CMD105 arguments differ')
    layout = [integer(args[0], 1, 1), integer(args[1], -1, 1), integer(args[2], -1, 3)]
    _guard.emit('p04f_native_transfer_request', source=code.co_filename, method=code.co_name,
                source_line=code.co_firstlineno, phase=phase, owner_id=id(values.get('self')),
                native_cmd=105, request_id=integer(values.get('requestID'), 1, 32767), layout=layout)


def native_event(fields):
    if _scenario is not None:
        _scenario.note_native(fields)


class _Screenshots(recruitment._Screenshots):
    def capture(self, name, record):
        allowed = ['p04f_transfer_initial', 'p04f_transfer_relogin'] + ['p04f_' + step[0] for step in STEPS]
        if name not in allowed:
            raise ValueError('unsupported transfer screenshot basename')
        if name not in self.requested:
            if any(entry.startswith(name + '_') for entry in self._entries()):
                raise ValueError('transfer screenshot basename occupied')
            import BigWorld
            self.requested.add(name)
            BigWorld.screenShot('png', name)
            record('p04f_transfer_screenshot_requested', basename=name, writer='BigWorld.screenShot')
        names = [entry for entry in self._entries() if re.match(r'\A' + re.escape(name) + r'_[0-9]{3,10}\.png\Z', entry)]
        if not names:
            return None
        if len(names) != 1:
            raise ValueError('ambiguous native transfer screenshot')
        from project_preferences import owned
        from ms1_crew_scenario import png_evidence
        path = owned(os.path.join(self.directory, names[0]), self.directory)
        if not os.path.isfile(path) or os.path.islink(path):
            raise ValueError('native transfer screenshot must be an owned regular file')
        return png_evidence(path, name)


class NativeScenario(object):
    def __init__(self, record, mode, expected, settings=None, clock=None):
        global _scenario
        if not callable(record) or mode not in ('transfer', 'relogin'):
            raise ValueError('explicit native transfer diagnostic mode required')
        self.expected = checked_expected(expected)
        if mode == 'transfer' and (self.expected['ms1_crew'] != [1, 3] or self.expected['free_quota'] != 0):
            raise ValueError('transfer diagnostic starts from the completed accepted recruitment')
        self.record, self.mode = record, mode
        self.clock = clock if clock is not None else time.monotonic if hasattr(time, 'monotonic') else time.clock
        self.started = self.clock()
        if type(self.started) not in (int, float) or math.isnan(self.started) or math.isinf(self.started):
            raise ValueError('finite native transfer clock required')
        self.last_time, self.advances, self.phase = self.started, 0, 'wait_hangar'
        self.step, self.pending, self.error = 0, None, None
        self.snapshot, self.ammo, self.ready_since = None, None, None
        self.captures = []
        self.screenshots = None if settings is None else _Screenshots(settings)
        if _scenario is not None and _scenario.phase not in ('complete', 'error'):
            raise RuntimeError('one active native transfer scenario required')
        _scenario = self

    def emit(self, event, **fields):
        fields.update(version=VERSION, policy=POLICY, step=self.step)
        self.record(event, **fields)

    def note_native(self, fields):
        """Called from passive profile recording; never performs GUI or network work."""
        if self.pending is None or self.error is not None:
            return
        try:
            event, pending = fields.get('event'), self.pending
            if event == 'p04f_native_transfer_request':
                if pending.get('request') is not None or fields.get('layout') != pending['layout']:
                    raise ValueError('unexpected native CMD105 command during diagnostic')
                pending['request'] = dict(fields)
            elif (event == 'p09d_native_ammo_call' and fields.get('method') == '_update'
                    and fields.get('phase') == 'return' and fields.get('has_inventory') is True):
                if pending.get('request') is None or pending.get('update') is not None:
                    raise ValueError('native inventory update without one transfer request')
                if (fields.get('owner_id') != pending['request']['owner_id']
                        or fields.get('revision') != fields.get('previous_revision', -2) + 1):
                    raise ValueError('native transfer update owner/revision mismatch')
                pending['update'] = dict(fields)
            elif (event == 'p09d_native_ammo_call' and fields.get('method') == 'onCmdResponseExt'
                    and fields.get('phase') == 'return' and pending.get('request') is not None
                    and fields.get('requestID') == pending['request']['request_id']):
                if (pending.get('update') is None or pending.get('success') is not None
                        or type(fields.get('resultID')) not in recruitment.integer_types or fields['resultID'] != 0
                        or fields.get('owner_id') != pending['request']['owner_id']):
                    raise ValueError('native transfer callback failed or preceded inventory update')
                pending['success'] = dict(fields)
        except (ValueError, KeyError, TypeError):
            self.error = 'native transfer request/update/success ordering or identity differs'

    def advance(self, ready_hangar):
        if type(ready_hangar) is not bool:
            raise ValueError('explicit native Hangar readiness required')
        if self.phase == 'complete':
            return True
        if self.phase == 'error':
            raise RuntimeError('failed transfer diagnostic cannot resume')
        try:
            now = self.clock()
            if (type(now) not in (int, float) or math.isnan(now) or math.isinf(now)
                    or now < self.last_time or now - self.started > 240):
                raise RuntimeError('finite native transfer deadline240s exceeded')
            self.last_time, self.advances = now, self.advances + 1
            if self.advances > 600 or self.error is not None:
                raise RuntimeError(self.error or 'native transfer observation budget exhausted')
            return self._advance(ready_hangar)
        except Exception:
            self.phase = 'error'
            raise

    def _advance(self, ready):
        if not ready:
            return False
        from gui.WindowsManager import g_windowsManager
        from gui.Scaleform.framework import ViewTypes
        from gui.Scaleform.Waiting import Waiting
        from CurrentVehicle import g_currentVehicle
        page = g_windowsManager.window.containerManager.getContainer(ViewTypes.LOBBY_SUB).getView()
        if type(page).__name__ != 'Hangar' or page.flashObject is None or page.crewPanel.flashObject is None:
            raise RuntimeError('original Flash-bound Hangar and Crew required')
        if Waiting.isVisible():
            return False
        if self.phase == 'wait_hangar':
            self.phase = 'wait_ms1'
            page.tankCarousel.vehicleChange(1)
            self.emit('p04f_transfer_select_ms1', original_callback='TankCarousel.vehicleChange')
            return False
        if g_currentVehicle.invID != 1:
            if self.phase == 'wait_ms1':
                return False
            raise RuntimeError('native vehicle changed during transfer scenario')
        if self.phase == 'wait_ms1':
            self.snapshot, self.ammo = native_snapshot(), native_ammunition()
            if self.snapshot != self.expected:
                raise RuntimeError('native initial or fresh-login assignment differs from exact expectation')
            self.phase, self.ready_since = 'initial_capture', self.last_time
            self.emit('p04f_transfer_initial', snapshot=self.snapshot, ammunition=self.ammo)
        if self.phase in ('initial_capture', 'after_capture'):
            if self.last_time - self.ready_since > 20:
                raise RuntimeError('native transfer screenshot deadline20s exceeded')
            if self.last_time - self.ready_since < 2:
                return False
            if native_snapshot() != self.snapshot or native_ammunition() != self.ammo:
                raise RuntimeError('native state changed while rendering transfer evidence')
            name = ('p04f_transfer_relogin' if self.mode == 'relogin' else 'p04f_transfer_initial') if self.phase == 'initial_capture' else 'p04f_' + STEPS[self.step][0]
            capture = None if self.screenshots is None else self.screenshots.capture(name, self.record)
            if self.screenshots is not None and capture is None:
                return False
            if capture is not None:
                self.captures.append(capture)
                self.emit('p04f_transfer_screenshot', screenshot=capture)
            if self.mode == 'relogin':
                self.emit('p04f_transfer_relogin', snapshot=self.snapshot, ammunition=self.ammo,
                          exact_snapshot_match=True, action='read_only')
                self.phase = 'complete'
                return True
            if self.phase == 'after_capture':
                self.step += 1
                self.pending = None
            if self.step == len(STEPS):
                self.emit('p04f_transfer_final', snapshot=self.snapshot, ammunition=self.ammo,
                          operations=len(STEPS), physical_pointer_input=False, pixels='NOT_RUN')
                self.phase = 'complete'
                return True
            self.phase = 'action'
        if self.phase == 'action':
            name, callback, args, slot, identity = STEPS[self.step]
            self.emit('p04f_transfer_before', name=name, snapshot=self.snapshot, ammunition=self.ammo)
            self.pending = dict(layout=[1, slot, identity], expected=projected_transfer(self.snapshot, slot, identity))
            self.phase = 'wait_result'
            self.emit('p04f_transfer_action', name=name, original_callback='Crew.' + callback,
                      arguments=list(args), native_cmd=105, layout=self.pending['layout'])
            getattr(page.crewPanel, callback)(*args)
            return False
        if self.phase == 'wait_result':
            if self.pending.get('success') is None:
                return False
            actual, ammo = native_snapshot(), native_ammunition()
            if actual != self.pending['expected'] or ammo != self.ammo:
                raise RuntimeError('native transfer changed identity/passport/quota/resources/ammunition or wrong assignments')
            self.snapshot = actual
            self.emit('p04f_transfer_callback', request_id=self.pending['request']['request_id'],
                      result=0, update_before_success=True, previous_revision=self.pending['update']['previous_revision'],
                      revision=self.pending['update']['revision'])
            self.emit('p04f_transfer_after', name=STEPS[self.step][0], snapshot=actual,
                      ammunition=ammo, action='native_inventory_readback')
            self.phase, self.ready_since = 'after_capture', self.last_time
        return False
