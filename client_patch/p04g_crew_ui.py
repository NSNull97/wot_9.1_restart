# -*- coding: utf-8 -*-
"""Source-bound two-vehicle crew UI; original processors/cache/network stay intact."""
import copy
import hashlib
import math
import os
import re
import time
import p04d_crew_ui as recruitment
import p04f_crew_ui as transfer

VERSION = 1
POLICY = 'test_lab.ms1_is7.existing_crew.assignment.v1'
NOTICE = u'Пересадка доступна для своих командира и механиков-водителей МС-1 и ИС-7. Сначала высадите танкиста в казарму.'
ROLES = {1: ('commander', 'driver'), 2: ('commander', 'gunner', 'driver', 'loader', 'loader')}
STEPS = (
    ('unload_ms1_commander', 1, 'unloadTankman', (1,), 0, -1),
    ('seat_is7_commander', 2, 'equipTankman', (1, 0), 0, 1),
    ('seat_ms1_driver3', 1, 'equipTankman', (3, 1), 1, 3),
    ('unload_ms1_driver3', 1, 'unloadTankman', (3,), 1, -1),
    ('seat_is7_driver3', 2, 'equipTankman', (3, 2), 2, 3),
    ('replace_is7_driver2', 2, 'equipTankman', (2, 2), 2, 2),
    ('unload_is7_commander', 2, 'unloadTankman', (1,), 0, -1),
    ('return_ms1_commander', 1, 'equipTankman', (1, 0), 0, 1),
    ('unload_is7_driver2', 2, 'unloadTankman', (2,), 2, -1),
    ('return_ms1_driver2', 1, 'equipTankman', (2, 1), 1, 2),
    ('seat_is7_driver3_again', 2, 'equipTankman', (3, 2), 2, 3),
    ('unload_is7_crew', 2, 'unloadAllTankman', (), -1, -1),
    ('unload_ms1_commander_final', 1, 'unloadTankman', (1,), 0, -1),
    ('seat_is7_commander_final', 2, 'equipTankman', (1, 0), 0, 1))
_guard = None
_scenario = None
integer = transfer.integer
native_ammunition = transfer.native_ammunition


def crew_key(vehicle):
    return 'ms1_crew' if integer(vehicle, 1, 2) == 1 else 'is7_crew'


def checked_expected(value):
    fields = set(('database_id', 'selected_inventory_id', 'free_quota', 'credits', 'gold',
                  'ms1_crew', 'is7_crew', 'tankmen'))
    row_fields = set(('inventory_id', 'vehicle_inventory_id', 'slot', 'sha256', 'nation_id',
                      'vehicle_type_id', 'role', 'role_level', 'no_skills', 'free_xp'))
    if type(value) is not dict or set(value) != fields:
        raise ValueError('exact native two-vehicle crew snapshot required')
    integer(value['database_id'], 1, 2147483647)
    integer(value['selected_inventory_id'], 1, 2)
    integer(value['free_quota'], 0, 0)
    for field in ('credits', 'gold'):
        integer(value[field], 0, 9223372036854775807)
    assignments = {}
    for vehicle in (1, 2):
        crew = value[crew_key(vehicle)]
        if type(crew) is not list or len(crew) != len(ROLES[vehicle]):
            raise ValueError('source-bound native vehicle crew shape differs')
        for slot, identity in enumerate(crew):
            if identity is not None:
                integer(identity, 1, 3)
                if identity in assignments:
                    raise ValueError('duplicate native assignment')
                assignments[identity] = (vehicle, slot)
    if type(value['tankmen']) is not list or len(value['tankmen']) != 3:
        raise ValueError('three accepted MS-1-trained identities required')
    for expected_id, member in enumerate(value['tankmen'], 1):
        if type(member) is not dict or set(member) != row_fields:
            raise ValueError('exact native tankman fields required')
        integer(member['inventory_id'], expected_id, expected_id)
        for field, fixed in (('nation_id', 0), ('vehicle_type_id', 13), ('role_level', 100), ('free_xp', 0)):
            integer(member[field], fixed, fixed)
        role = 'commander' if expected_id == 1 else 'driver'
        pin = transfer.COMMANDER_SHA256 if expected_id == 1 else recruitment.DRIVER_SHA256
        if member['role'] != role or member['sha256'] != pin or member['no_skills'] is not True:
            raise ValueError('native training identity/passport changed')
        actual = (integer(member['vehicle_inventory_id'], -1, 2), integer(member['slot'], -1, 4))
        assignment = assignments.get(expected_id, (-1, -1))
        if actual != assignment or actual[0] != -1 and ROLES[actual[0]][actual[1]] != role:
            raise ValueError('native assignment or primary role mismatch')
    return copy.deepcopy(value)


def native_snapshot():
    from gui.shared import g_itemsCache
    value = recruitment.native_snapshot()
    vehicle = g_itemsCache.items.getVehicle(2)
    if vehicle is None or vehicle.intCD != 7169:
        raise ValueError('original source-bound IS-7 inventory required')
    crew = sorted(vehicle.crew, key=lambda pair: pair[0])
    if len(crew) != 5 or [pair[0] for pair in crew] != [0, 1, 2, 3, 4]:
        raise ValueError('original five-seat IS-7 crew required')
    value['is7_crew'] = [None if item is None else integer(item.invID, 1, 3) for slot, item in crew]
    return checked_expected(value)


def native_efficiency(snapshot):
    """Observe original GUI efficiency, separate from immutable training descriptors."""
    from gui.shared import g_itemsCache
    result = []
    for member in checked_expected(snapshot)['tankmen']:
        item = g_itemsCache.items.getTankman(member['inventory_id'])
        actual = item.efficiencyRoleLevel
        if (type(actual) not in recruitment.integer_types + (float,)
                or not 0 <= actual <= 100 or int(actual) != actual):
            raise ValueError('finite integral native efficiency level required')
        expected = 50 if member['vehicle_inventory_id'] == 2 else 100
        if int(actual) != expected or item.vehicleInvID != member['vehicle_inventory_id']:
            raise ValueError('original native specialization efficiency differs')
        result.append(dict(inventory_id=member['inventory_id'], vehicle_inventory_id=item.vehicleInvID,
                           trained_vehicle_type_id=member['vehicle_type_id'], base_role_level=member['role_level'],
                           efficiency_role_level=int(actual)))
    return result


def projected_transfer(before, vehicle, slot, identity):
    """Diagnostic expectation only; never writes original GUI items or network state."""
    value = checked_expected(before)
    integer(vehicle, 1, 2)
    integer(slot, -1, len(ROLES[vehicle]) - 1)
    integer(identity, -1, 3)
    if identity == 0 or slot == -1 and identity != -1:
        raise ValueError('invalid native assignment sentinel')
    if identity > 0:
        # The native dropdown excludes tankmen seated on any other vehicle.
        member = value['tankmen'][identity - 1]
        if member['vehicle_inventory_id'] != -1 or member['role'] != ROLES[vehicle][slot]:
            raise ValueError('native UI candidate must be a compatible barracks tankman')
    key = crew_key(vehicle)
    if slot == -1:
        value[key] = [None] * len(ROLES[vehicle])
    else:
        value[key][slot] = None if identity == -1 else identity
    for member in value['tankmen']:
        member['vehicle_inventory_id'], member['slot'] = -1, -1
        for owner in (1, 2):
            crew = value[crew_key(owner)]
            if member['inventory_id'] in crew:
                member['vehicle_inventory_id'], member['slot'] = owner, crew.index(member['inventory_id'])
    return checked_expected(value)


class _CrossGuard(transfer._TransferGuard):
    def __init__(self, classes, messages, record, snapshot=None):
        transfer._TransferGuard.__init__(self, classes, messages, record,
                                       native_snapshot if snapshot is None else snapshot)

    def emit(self, event, **fields):
        if self.events >= 2048 and not event.endswith('_policy'):
            raise RuntimeError('cross-vehicle crew event budget exhausted')
        self.events += 1
        fields.update(version=VERSION, policy=POLICY)
        self.record(event.replace('p04f_transfer', 'p04g_cross'), **fields)

    def _deny(self, callback):
        self.emit('p04g_cross_denied', callback=callback, original_callback_called=False)
        if self.messages.g_instance is None:
            raise RuntimeError('original SystemMessages unavailable')
        self.messages.pushMessage(NOTICE, type=self.messages.SM_TYPE.Warning)

    def _wrapper(self, original, callback, name, static):
        guard = self
        def wrapped(*args, **kwargs):
            if not guard.active:
                raise RuntimeError('cross-vehicle crew callback after cleanup')
            supplied = args if static else args[1:]
            try:
                if kwargs or not static and not args:
                    raise ValueError('original positional callback required')
                state = checked_expected(guard.snapshot())
                vehicle = state['selected_inventory_id']
                if name == 'equipTankman':
                    if len(supplied) != 2:
                        raise ValueError('equip callback arity')
                    identity = transfer.callback_integer(supplied[0], 1, 3)
                    slot = transfer.callback_integer(supplied[1], 0, 3)
                    projected_transfer(state, vehicle, slot, identity)
                elif name == 'unloadTankman':
                    if len(supplied) != 1:
                        raise ValueError('unload callback arity')
                    member = state['tankmen'][transfer.callback_integer(supplied[0], 1, 3) - 1]
                    if callback == 'Barracks.unloadTankman':
                        vehicle = member['vehicle_inventory_id']
                    if vehicle not in (1, 2) or member['vehicle_inventory_id'] != vehicle:
                        raise ValueError('tankman is not seated in the original target vehicle')
                    slot, identity = member['slot'], -1
                else:
                    if supplied or all(item is None for item in state[crew_key(vehicle)]):
                        raise ValueError('whole crew unload requires existing assigned crew')
                    slot, identity = -1, -1
            except ValueError:
                return guard._deny(callback)
            guard.emit('p04g_cross_ui_call', callback=callback, vehicle=vehicle, slot=slot,
                       tankman_id=identity, native_cmd=105, original_callback_called=True)
            return original(*args, **kwargs)
        return wrapped


def init(record):
    global _guard
    import crew_capabilities
    from gui.Scaleform.daapi.view.lobby.hangar.Crew import Crew
    from gui.Scaleform.daapi.view.lobby.barracks.Barracks import Barracks
    from gui import SystemMessages
    capability = crew_capabilities._guard
    if (_guard is not None or transfer._guard is not None or capability is None or not capability.active
            or capability.allow_cross_vehicle is not True):
        raise RuntimeError('explicit exclusive cross-vehicle capability required')
    classes = dict(Crew=Crew, Barracks=Barracks)
    if any((row[0], row[1]) in [(classes[a], b) for a, b, _ in transfer.TARGETS] for row in capability.bindings):
        raise RuntimeError('cross-vehicle callbacks still restricted by capability policy')
    candidate = _CrossGuard(classes, SystemMessages, record)
    candidate.install()
    _guard = candidate


def fini():
    global _guard, _scenario
    if _guard is not None:
        _guard.restore()
        _guard = None
    _scenario = None


def observe_profile(frame, phase):
    code, values = frame.f_code, frame.f_locals
    if (phase != 'return' or code.co_filename != 'scripts/client/Account.py'
            or code.co_name != '__doCmd' or values.get('cmd') != 105):
        return
    if (code.co_firstlineno != 1523 or hashlib.sha256(code.co_code).hexdigest()
            != 'efb40e1d1742e98179a41a6d907f06ec749d64f1e6419c414fe702535f42ec36'):
        raise RuntimeError('native cross-vehicle Account command source differs')
    if _guard is None or not _guard.active:
        raise RuntimeError('native observation requires active cross-vehicle policy')
    args = values.get('args')
    if type(args) is not tuple or len(args) != 3:
        raise ValueError('native CMD105 arguments differ')
    layout = [integer(args[0], 1, 2), integer(args[1], -1, 4), integer(args[2], -1, 3)]
    _guard.emit('p04g_native_cross_request', source=code.co_filename, method=code.co_name,
                source_line=code.co_firstlineno, phase=phase, owner_id=id(values.get('self')),
                native_cmd=105, request_id=integer(values.get('requestID'), 1, 32767), layout=layout)


def native_event(fields):
    if _scenario is not None:
        _scenario.note_native(fields)


class _Screenshots(recruitment._Screenshots):
    def capture(self, name, record):
        allowed = ['p04g_cross_initial', 'p04g_cross_relogin_ms1', 'p04g_cross_relogin_is7']
        allowed += ['p04g_' + step[0] for step in STEPS]
        if name not in allowed:
            raise ValueError('unsupported cross-vehicle screenshot basename')
        if name not in self.requested:
            if any(entry.startswith(name + '_') for entry in self._entries()):
                raise ValueError('cross-vehicle screenshot basename occupied')
            import BigWorld
            self.requested.add(name)
            BigWorld.screenShot('png', name)
            record('p04g_cross_screenshot_requested', basename=name, writer='BigWorld.screenShot')
        names = [entry for entry in self._entries() if re.match(r'\A' + re.escape(name) + r'_[0-9]{3,10}\.png\Z', entry)]
        if not names:
            return None
        if len(names) != 1:
            raise ValueError('ambiguous native cross-vehicle screenshot')
        from project_preferences import owned
        from ms1_crew_scenario import png_evidence
        path = owned(os.path.join(self.directory, names[0]), self.directory)
        if not os.path.isfile(path) or os.path.islink(path):
            raise ValueError('native cross-vehicle screenshot must be an owned regular file')
        return png_evidence(path, name)


class NativeScenario(transfer.NativeScenario):
    def __init__(self, record, mode, expected, settings=None, clock=None):
        global _scenario
        if not callable(record) or mode not in ('transfer', 'relogin'):
            raise ValueError('explicit cross-vehicle diagnostic mode required')
        self.expected = checked_expected(expected)
        if mode == 'transfer' and (self.expected['ms1_crew'] != [1, None]
                or self.expected['is7_crew'] != [None] * 5 or self.expected['selected_inventory_id'] != 1):
            raise ValueError('cross-vehicle diagnostic requires accepted P04F partial crew')
        self.record, self.mode = record, mode
        self.clock = clock if clock is not None else time.monotonic if hasattr(time, 'monotonic') else time.clock
        self.started = self.clock()
        if type(self.started) not in (int, float) or math.isnan(self.started) or math.isinf(self.started):
            raise ValueError('finite native diagnostic clock required')
        self.last_time, self.advances, self.phase = self.started, 0, 'wait_hangar'
        self.step, self.pending, self.error = 0, None, None
        self.snapshot, self.ammo, self.ready_since = None, None, None
        self.captures, self.relogin_views = [], []
        self.screenshots = None if settings is None else _Screenshots(settings)
        self.selected, self.selection_ready, self.after_selection = None, None, None
        if _scenario is not None and _scenario.phase not in ('complete', 'error'):
            raise RuntimeError('one active native cross-vehicle scenario required')
        _scenario = self

    def emit(self, event, **fields):
        fields.update(version=VERSION, policy=POLICY, step=self.step)
        self.record(event, **fields)

    def note_native(self, fields):
        if fields.get('event') == 'p04g_native_cross_request':
            fields = dict(fields, event='p04f_native_transfer_request')
        transfer.NativeScenario.note_native(self, fields)

    def _select(self, page, vehicle, following):
        self.selected, self.after_selection, self.selection_ready = vehicle, following, None
        self.phase = 'wait_selection'
        page.tankCarousel.vehicleChange(vehicle)
        self.emit('p04g_cross_select', vehicle=vehicle, original_callback='TankCarousel.vehicleChange')

    def _advance(self, ready):
        if not ready:
            self.selection_ready = None
            return False
        from gui.WindowsManager import g_windowsManager
        from gui.Scaleform.framework import ViewTypes
        from gui.Scaleform.Waiting import Waiting
        from CurrentVehicle import g_currentVehicle
        page = g_windowsManager.window.containerManager.getContainer(ViewTypes.LOBBY_SUB).getView()
        if type(page).__name__ != 'Hangar' or page.flashObject is None or page.crewPanel.flashObject is None:
            raise RuntimeError('original Flash-bound Hangar and Crew required')
        if Waiting.isVisible():
            self.selection_ready = None
            return False
        if self.phase == 'wait_hangar':
            target = 1 if self.mode == 'transfer' else 3 - self.expected['selected_inventory_id']
            self._select(page, target, 'initial_capture')
            return False
        if g_currentVehicle.invID != self.selected:
            if self.phase == 'wait_selection':
                self.selection_ready = None
                return False
            raise RuntimeError('native vehicle changed during cross-vehicle scenario')
        if self.phase == 'wait_selection':
            if self.selection_ready is None:
                self.selection_ready = self.last_time
            if self.last_time - self.selection_ready < 2:
                return False
            actual, ammo = native_snapshot(), native_ammunition()
            expected = dict(self.expected if self.snapshot is None else self.snapshot,
                            selected_inventory_id=self.selected)
            if actual != expected or self.ammo is not None and ammo != self.ammo:
                raise RuntimeError('native selection changed exact crew or ammunition state')
            self.snapshot, self.ammo = actual, ammo
            self.phase, self.ready_since = self.after_selection, self.last_time
            if self.phase == 'initial_capture':
                self.emit('p04g_cross_initial', snapshot=actual, ammunition=ammo, efficiency=native_efficiency(actual))
        if self.phase in ('initial_capture', 'after_capture', 'relogin_capture'):
            if self.last_time - self.ready_since > 20:
                raise RuntimeError('native cross-vehicle screenshot deadline20s exceeded')
            if self.last_time - self.ready_since < 2:
                return False
            if native_snapshot() != self.snapshot or native_ammunition() != self.ammo:
                raise RuntimeError('native state changed while rendering cross-vehicle evidence')
            efficiency = native_efficiency(self.snapshot)
            if self.mode == 'relogin':
                name = 'p04g_cross_relogin_' + ('ms1' if self.selected == 1 else 'is7')
            else:
                name = 'p04g_cross_initial' if self.phase == 'initial_capture' else 'p04g_' + STEPS[self.step][0]
            capture = None if self.screenshots is None else self.screenshots.capture(name, self.record)
            if self.screenshots is not None and capture is None:
                return False
            if capture is not None:
                self.captures.append(capture)
                self.emit('p04g_cross_screenshot', screenshot=capture, vehicle=self.selected)
            if self.mode == 'relogin':
                self.relogin_views.append(self.selected)
                self.emit('p04g_cross_relogin_view', vehicle=self.selected, snapshot=self.snapshot, efficiency=efficiency)
                if len(self.relogin_views) == 1:
                    self._select(page, self.expected['selected_inventory_id'], 'relogin_capture')
                    return False
                if self.snapshot != self.expected or set(self.relogin_views) != set((1, 2)):
                    raise RuntimeError('fresh login did not verify both native crew views')
                self.emit('p04g_cross_relogin', snapshot=self.snapshot, ammunition=self.ammo, efficiency=efficiency,
                          exact_snapshot_match=True, vehicles_observed=self.relogin_views, action='read_only')
                self.phase = 'complete'
                return True
            if self.phase == 'after_capture':
                self.step += 1
                self.pending = None
            if self.step == len(STEPS):
                self.emit('p04g_cross_final', snapshot=self.snapshot, ammunition=self.ammo, efficiency=efficiency,
                          operations=len(STEPS), physical_pointer_input=False, pixels='NOT_RUN')
                self.phase = 'complete'
                return True
            if STEPS[self.step][1] != self.selected:
                self._select(page, STEPS[self.step][1], 'action')
                return False
            self.phase = 'action'
        if self.phase == 'action':
            name, vehicle, callback, args, slot, identity = STEPS[self.step]
            if vehicle != self.selected or native_snapshot() != self.snapshot:
                raise RuntimeError('native callback target or state changed')
            self.emit('p04g_cross_before', name=name, snapshot=self.snapshot, ammunition=self.ammo,
                      efficiency=native_efficiency(self.snapshot))
            self.pending = dict(layout=[vehicle, slot, identity],
                                expected=projected_transfer(self.snapshot, vehicle, slot, identity))
            self.phase = 'wait_result'
            self.emit('p04g_cross_action', name=name, original_callback='Crew.' + callback,
                      arguments=list(args), native_cmd=105, layout=self.pending['layout'])
            getattr(page.crewPanel, callback)(*args)
            return False
        if self.phase == 'wait_result':
            if self.pending.get('success') is None:
                return False
            actual, ammo = native_snapshot(), native_ammunition()
            if actual != self.pending['expected'] or ammo != self.ammo:
                raise RuntimeError('native assignments/passports/quota/resources/ammunition changed unexpectedly')
            self.snapshot = actual
            self.emit('p04g_cross_callback', request_id=self.pending['request']['request_id'], result=0,
                      update_before_success=True, previous_revision=self.pending['update']['previous_revision'],
                      revision=self.pending['update']['revision'])
            self.emit('p04g_cross_after', name=STEPS[self.step][0], snapshot=actual, ammunition=ammo,
                      efficiency=native_efficiency(actual), action='native_inventory_readback')
            self.phase, self.ready_since = 'after_capture', self.last_time
        return False
