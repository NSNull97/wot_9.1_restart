# -*- coding: utf-8 -*-
"""Bounded #717 roster readback and passive native command correlation.

The selected H tariff policy is supplied explicitly by the caller. These
readers do not create descriptors, allocate identities or change native caches.
Original callback integration is installed separately after policy selection.
"""
import copy
import hashlib
import math
import re
import os
import time

import p04d_crew_ui as recruitment
import p04f_crew_ui as transfer
import p04g_crew_ui as cross

VERSION = 1
POLICY = 'test_lab.ms1_is7.roster.free50.capacity16.v1'
ROLE_LEVEL = 50
LABEL = u'50%%, бесплатно: %d'
NOTICE = u'Тестовый найм: МС-1 и ИС-7, обучение 50%, бесплатно в пределах серверной квоты. Платный найм и навыки недоступны.'
MAX_TANKMEN = 16
VEHICLES = {
    1: (3329, 13, 'lightTank', ('commander', 'driver')),
    2: (7169, 28, 'heavyTank', ('commander', 'gunner', 'driver', 'loader', 'loader')),
}
ROW_FIELDS = set(('inventory_id', 'vehicle_inventory_id', 'slot', 'sha256',
                  'nation_id', 'vehicle_type_id', 'role', 'role_level', 'no_skills', 'free_xp'))
SNAPSHOT_FIELDS = set(('database_id', 'selected_inventory_id', 'free_quota',
                       'credits', 'gold', 'ms1_crew', 'is7_crew', 'tankmen'))
COMMAND_PIN = (1523, 'efb40e1d1742e98179a41a6d907f06ec749d64f1e6419c414fe702535f42ec36')
HIRES = ((1, 0, 'commander'), (1, 1, 'driver'), (2, 0, 'commander'),
         (2, 1, 'gunner'), (2, 2, 'driver'), (2, 3, 'loader'), (2, 4, 'loader'))
STEPS = tuple(('hire_%s_%d' % ('ms1' if vehicle == 1 else 'is7', slot), vehicle,
               'buyTankman', (), slot, 4 + index) for index, (vehicle, slot, role) in enumerate(HIRES)) + (
    ('unload_loader10', 2, 'unloadTankman', (10,), 4, -1),
    ('replace_loader9', 2, 'equipTankman', (10, 3), 3, 10),
    ('reseat_loader9', 2, 'equipTankman', (9, 4), 4, 9))
_recruit_guard = None
_transfer_guard = None
_scenario = None
_record = None


def integer(value, low, high):
    return recruitment._integer(value, low, high)


def checked_expected(value, role_level=None):
    """Validate roster structure; a supplied level also binds new H members.

    Old identities keep their accepted, pinned descriptors. New descriptor
    hashes remain part of the caller's exact expected snapshot/catalog rather
    than an invented local descriptor generator.
    """
    if type(value) is not dict or set(value) != SNAPSHOT_FIELDS:
        raise ValueError('exact native roster snapshot required')
    if role_level is not None:
        integer(role_level, 0, 100)
    integer(value['database_id'], 1, 2147483647)
    integer(value['selected_inventory_id'], 1, 2)
    integer(value['free_quota'], 0, MAX_TANKMEN)
    for field in ('credits', 'gold'):
        integer(value[field], 0, 9223372036854775807)
    members = value['tankmen']
    if type(members) is not list or not 3 <= len(members) <= MAX_TANKMEN:
        raise ValueError('bounded native roster membership required')
    seats = {}
    for vehicle, field in ((1, 'ms1_crew'), (2, 'is7_crew')):
        crew = value[field]
        if type(crew) is not list or len(crew) != len(VEHICLES[vehicle][3]):
            raise ValueError('source-bound native crew shape required')
        for slot, identity in enumerate(crew):
            if identity is None:
                continue
            integer(identity, 1, MAX_TANKMEN)
            if identity in seats:
                raise ValueError('tankman occupies more than one native seat')
            seats[identity] = (vehicle, slot)
    for identity, row in enumerate(members, 1):
        if type(row) is not dict or set(row) != ROW_FIELDS:
            raise ValueError('exact native roster row required')
        integer(row['inventory_id'], 1, MAX_TANKMEN)
        if row['inventory_id'] != identity:
            raise ValueError('retained contiguous server roster identities required')
        integer(row['nation_id'], 0, 0)
        integer(row['vehicle_type_id'], 1, 255)
        if row['vehicle_type_id'] not in (13, 28):
            raise ValueError('unsupported trained vehicle type')
        integer(row['role_level'], 0, 100)
        if row['role'] not in ('commander', 'driver', 'gunner', 'loader'):
            raise ValueError('unsupported primary crew role')
        if (not isinstance(row['sha256'], recruitment.string_types)
                or re.match(r'\A[0-9a-f]{64}\Z', row['sha256']) is None
                or row['no_skills'] is not True):
            raise ValueError('native descriptor hash and empty skills required')
        integer(row['free_xp'], 0, 0)
        integer(row['vehicle_inventory_id'], -1, 2)
        integer(row['slot'], -1, 4)
        actual = (row['vehicle_inventory_id'], row['slot'])
        if actual != seats.get(identity, (-1, -1)):
            raise ValueError('native tankman and vehicle assignments disagree')
        if actual[0] != -1 and row['role'] != VEHICLES[actual[0]][3][actual[1]]:
            raise ValueError('native primary role does not match seat')
        if identity <= 3:
            role = 'commander' if identity == 1 else 'driver'
            pin = transfer.COMMANDER_SHA256 if identity == 1 else recruitment.DRIVER_SHA256
            if (row['vehicle_type_id'] != 13 or row['role'] != role
                    or row['role_level'] != 100 or row['sha256'] != pin):
                raise ValueError('accepted original tankman descriptor changed')
        elif role_level is not None and row['role_level'] != role_level:
            raise ValueError('new tankman level differs from selected policy')
    if set(seats) - set(range(1, len(members) + 1)):
        raise ValueError('vehicle references an absent native tankman')
    return copy.deepcopy(value)


def native_snapshot(role_level=None):
    import BigWorld
    from ConnectionManager import connectionManager
    from CurrentVehicle import g_currentVehicle
    from gui.shared import g_itemsCache
    from gui.shared.gui_items import ItemsCollection
    if BigWorld.player() is None or not connectionManager.isConnected() or not g_itemsCache.isSynced():
        raise RuntimeError('native roster requires connected synced Account')
    items = g_itemsCache.items
    tankmen = items.getTankmen()
    if not isinstance(tankmen, ItemsCollection) or not 3 <= len(tankmen) <= MAX_TANKMEN:
        raise ValueError('bounded original ItemsCollection required')
    rows = []
    for identity, item in sorted(tankmen.items()):
        integer(identity, 1, MAX_TANKMEN)
        compact, desc = item.strCD, item.descriptor
        if (not isinstance(compact, bytes) or len(compact) != 25
                or desc.makeCompactDescr() != compact or item.invID != identity):
            raise ValueError('original descriptor parse/repack or identity differs')
        rows.append(dict(inventory_id=identity, vehicle_inventory_id=item.vehicleInvID,
                         slot=item.vehicleSlotIdx, sha256=hashlib.sha256(compact).hexdigest(),
                         nation_id=desc.nationID, vehicle_type_id=desc.vehicleTypeID,
                         role=desc.role, role_level=desc.roleLevel,
                         no_skills=not desc.skills, free_xp=desc.freeXP))
    value = dict(database_id=BigWorld.player().databaseID,
                 selected_inventory_id=g_currentVehicle.invID,
                 free_quota=items.stats.freeTankmenLeft, credits=items.stats.credits,
                 gold=items.stats.gold, tankmen=rows)
    for vehicle_id, field in ((1, 'ms1_crew'), (2, 'is7_crew')):
        vehicle = items.getVehicle(vehicle_id)
        if (vehicle is None or vehicle.invID != vehicle_id or vehicle.intCD != VEHICLES[vehicle_id][0]
                or tuple(roles[0] for roles in vehicle.descriptor.type.crewRoles) != VEHICLES[vehicle_id][3]):
            raise ValueError('source-bound original vehicle profile differs')
        crew = sorted(vehicle.crew, key=lambda pair: pair[0])
        if [pair[0] for pair in crew] != list(range(len(VEHICLES[vehicle_id][3]))):
            raise ValueError('original vehicle crew slots differ')
        value[field] = [None if member is None else member.invID for slot, member in crew]
    return checked_expected(value, role_level)


def native_readiness(snapshot):
    """Original isCrewFull is False or a truthy slot count, not strict bool."""
    from gui.shared import g_itemsCache
    snapshot = checked_expected(snapshot)
    result = []
    for identity, field in ((1, 'ms1_crew'), (2, 'is7_crew')):
        vehicle = g_itemsCache.items.getVehicle(identity)
        raw = vehicle.isCrewFull
        full = all(member is not None for member in snapshot[field])
        if type(raw) not in recruitment.integer_types + (bool,) or bool(raw) != full:
            raise ValueError('original crew fullness disagrees with native slots')
        result.append(dict(vehicle_inventory_id=identity, is_crew_full=bool(raw),
                           original_value=raw, battle_admission=False))
    return result


def native_efficiency(snapshot):
    """Read the original property; no local replacement of native crew math."""
    from gui.shared import g_itemsCache
    snapshot = checked_expected(snapshot)
    result = []
    for row in snapshot['tankmen']:
        item = g_itemsCache.items.getTankman(row['inventory_id'])
        value = item.efficiencyRoleLevel
        if (type(value) not in recruitment.integer_types + (float,)
                or math.isnan(value) or math.isinf(value) or int(value) != value
                or not 0 <= value <= 100 or item.vehicleInvID != row['vehicle_inventory_id']):
            raise ValueError('bounded integral original crew efficiency required')
        result.append(dict(inventory_id=row['inventory_id'], vehicle_inventory_id=item.vehicleInvID,
                           trained_vehicle_type_id=row['vehicle_type_id'], base_role_level=row['role_level'],
                           efficiency_role_level=int(value)))
    return result


def command_observation(frame, phase):
    """Inspect original __doCmd return after it allocates the request ID."""
    code, values = frame.f_code, frame.f_locals
    if (phase != 'return' or code.co_filename != 'scripts/client/Account.py'
            or code.co_name != '__doCmd' or values.get('cmd') not in (105, 309)):
        return None
    if (code.co_firstlineno, hashlib.sha256(code.co_code).hexdigest()) != COMMAND_PIN:
        raise RuntimeError('original roster command observer source differs')
    command, args = values['cmd'], values.get('args')
    if type(args) is not tuple or len(args) != (4 if command == 309 else 3):
        raise ValueError('original roster command argument shape differs')
    if command == 309:
        layout = [integer(args[0], 1, 2147483647), integer(args[1], 1, 2),
                  integer(args[2], 0, len(VEHICLES[args[1]][3]) - 1), integer(args[3], 0, 2)]
    else:
        vehicle = integer(args[0], 1, 2)
        layout = [vehicle, integer(args[1], -1, len(VEHICLES[vehicle][3]) - 1),
                  integer(args[2], -1, MAX_TANKMEN)]
        if layout[2] == 0 or layout[1] == -1 and layout[2] != -1:
            raise ValueError('original transfer sentinel differs')
    return dict(source=code.co_filename, source_line=code.co_firstlineno,
                method=code.co_name, phase=phase, owner_id=id(values.get('self')),
                native_cmd=command, request_id=integer(values.get('requestID'), 1, 32767), layout=layout)


class NativeCommandTracker(object):
    """Correlate one actual command, inventory update and original callback."""
    def __init__(self, command, layout):
        if command not in (105, 309) or type(layout) is not list or len(layout) != (4 if command == 309 else 3):
            raise ValueError('one explicit roster command layout required')
        self.command, self.layout = command, list(layout)
        self.request, self.update, self.success = None, None, None

    def observe(self, fields):
        event = fields.get('event')
        if event == 'p04h_native_roster_request':
            if (self.request is not None or fields.get('native_cmd') != self.command
                    or fields.get('layout') != self.layout):
                raise ValueError('unexpected or repeated native roster request')
            integer(fields.get('request_id'), 1, 32767)
            self.request = dict(fields)
        elif (event == 'p09d_native_ammo_call' and fields.get('method') == '_update'
                and fields.get('phase') == 'return' and fields.get('has_inventory') is True):
            if (self.request is None or self.update is not None
                    or fields.get('owner_id') != self.request.get('owner_id')):
                raise ValueError('native roster update has no unique matching request')
            old = integer(fields.get('previous_revision'), 1, 2147483646)
            if integer(fields.get('revision'), 2, 2147483647) != old + 1:
                raise ValueError('native roster update cursor differs')
            self.update = dict(fields)
        elif (event == 'p09d_native_ammo_call' and fields.get('method') == 'onCmdResponseExt'
                and fields.get('phase') == 'return' and self.request is not None
                and fields.get('requestID') == self.request.get('request_id')):
            if (self.update is None or self.success is not None
                    or fields.get('owner_id') != self.request.get('owner_id')):
                raise ValueError('native roster callback precedes update or repeats')
            integer(fields.get('resultID'), 0, 0)
            self.success = dict(fields)

    def receipt(self):
        if self.request is None or self.update is None or self.success is None:
            raise RuntimeError('native roster request/update/callback not complete')
        return dict(native_cmd=self.command, layout=list(self.layout), request_id=self.request['request_id'],
                    previous_revision=self.update['previous_revision'], revision=self.update['revision'],
                    result=0, update_before_success=True)


def crew_key(vehicle):
    return 'ms1_crew' if integer(vehicle, 1, 2) == 1 else 'is7_crew'


def callback_integer(value, low, high):
    if type(value) in recruitment.integer_types + (float,):
        if math.isnan(value) or math.isinf(value) or int(value) != value:
            raise ValueError('finite integral native callback argument required')
        return integer(int(value), low, high)
    if isinstance(value, recruitment.string_types) and re.match(r'\A[0-9]{1,2}\Z', value):
        return integer(int(value), low, high)
    raise ValueError('native callback integer required')


def _assignments(value):
    for row in value['tankmen']:
        row['vehicle_inventory_id'], row['slot'] = -1, -1
        for owner in (1, 2):
            crew = value[crew_key(owner)]
            if row['inventory_id'] in crew:
                row['vehicle_inventory_id'], row['slot'] = owner, crew.index(row['inventory_id'])


def projected_transfer(snapshot, vehicle, slot, identity):
    """Expected evidence only; never writes a GUI object or native cache."""
    value = checked_expected(snapshot, ROLE_LEVEL)
    vehicle = integer(vehicle, 1, 2)
    slot = integer(slot, -1, len(VEHICLES[vehicle][3]) - 1)
    identity = integer(identity, -1, len(value['tankmen']))
    crew = value[crew_key(vehicle)]
    if identity == 0 or slot == -1 and identity != -1:
        raise ValueError('unsupported native transfer selection')
    if identity > 0:
        row = value['tankmen'][identity - 1]
        if row['vehicle_inventory_id'] != -1:
            raise ValueError('original selectable candidate must be in barracks')
        if row['role'] != VEHICLES[vehicle][3][slot]:
            raise ValueError('primary role does not match target seat')
        crew[slot] = identity
    elif slot == -1:
        if all(member is None for member in crew):
            raise ValueError('whole crew is already empty')
        crew[:] = [None] * len(crew)
    else:
        if crew[slot] is None:
            raise ValueError('target seat is already empty')
        crew[slot] = None
    _assignments(value)
    return checked_expected(value, ROLE_LEVEL)


def checked_hires(rows):
    if type(rows) is not list or len(rows) != len(HIRES):
        raise ValueError('seven exact source-bound hire descriptor rows required')
    for index, (row, target) in enumerate(zip(rows, HIRES)):
        vehicle, slot, role = target
        expected = dict(inventory_id=4 + index, vehicle_inventory_id=vehicle, slot=slot,
                        nation_id=0, vehicle_type_id=VEHICLES[vehicle][1], role=role,
                        role_level=ROLE_LEVEL, no_skills=True, free_xp=0)
        if (type(row) is not dict or set(row) != ROW_FIELDS
                or any((not isinstance(row[k], recruitment.string_types) if isinstance(v, recruitment.string_types)
                        else type(row[k]) is not type(v)) or row[k] != v for k, v in expected.items())
                or not isinstance(row['sha256'], recruitment.string_types)
                or re.match(r'\A[0-9a-f]{64}\Z', row['sha256']) is None):
            raise ValueError('hire descriptor catalog differs from selected role/seat/level policy')
    return copy.deepcopy(rows)


def projected_recruit(snapshot, row):
    value = checked_expected(snapshot, ROLE_LEVEL)
    index = len(value['tankmen']) - 3
    if not 0 <= index < len(HIRES) or value['free_quota'] <= 0:
        raise ValueError('diagnostic recruitment count/quota exhausted')
    vehicle, slot, role = HIRES[index]
    if (row['inventory_id'] != len(value['tankmen']) + 1 or row['vehicle_inventory_id'] != vehicle
            or row['slot'] != slot or row['role'] != role):
        raise ValueError('diagnostic hire target or server identity differs')
    value['tankmen'].append(dict(row))
    value[crew_key(vehicle)][slot] = row['inventory_id']
    value['free_quota'] -= 1
    _assignments(value)
    return checked_expected(value, ROLE_LEVEL)


def target_data(vehicle, slot):
    vehicle = integer(vehicle, 1, 2)
    slot = integer(slot, 0, len(VEHICLES[vehicle][3]) - 1)
    return dict(nationID=0, tankType=VEHICLES[vehicle][2], typeID=VEHICLES[vehicle][1],
                roleType=VEHICLES[vehicle][3][slot], slot=slot)


def target_matches(data, vehicle):
    if type(data) is not dict or len(data) > 64:
        return False
    try:
        slot = callback_integer(data.get('slot'), 0, len(VEHICLES[vehicle][3]) - 1)
        expected = target_data(vehicle, slot)
        return all(recruitment._number_equals(data.get(key), item) if type(item) is int
                   else data.get(key) == item for key, item in expected.items())
    except (ValueError, KeyError):
        return False


class _Native(object):
    def state(self):
        return native_snapshot(ROLE_LEVEL)


class _RosterRecruitGuard(recruitment._RecruitGuard):
    def __init__(self, business_class, window_class, messages, record, native=None):
        self.window, self.windows = None, []
        recruitment._RecruitGuard.__init__(self, business_class, window_class, messages, record,
                                           _Native() if native is None else native)

    def emit(self, event, **fields):
        if self.events >= 2048 and not event.endswith('_policy'):
            raise RuntimeError('roster recruitment event budget exhausted')
        self.events += 1
        fields.update(version=VERSION, policy=POLICY)
        self.record(event.replace('p04d_recruit', 'p04h_roster'), **fields)

    def _state(self):
        if not self.active:
            raise RuntimeError('roster callback after cleanup')
        return checked_expected(self.native.state(), ROLE_LEVEL)

    def _deny(self, reason):
        self.emit('p04h_roster_denied', reason=reason, original_callback_called=False)
        if self.messages.g_instance is None:
            raise RuntimeError('original SystemMessages unavailable')
        self.messages.pushMessage(NOTICE, type=self.messages.SM_TYPE.Warning)

    def _open(self, original):
        guard = self
        def open_window(owner, event):
            state, ctx = guard._state(), event.ctx
            vehicle = state['selected_inventory_id']
            if (type(ctx) is not dict or len(ctx) > 16 or ctx.get('menuEnabled') is not False
                    or not recruitment._number_equals(ctx.get('currentVehicleId'), vehicle)
                    or not target_matches(ctx.get('data'), vehicle)):
                return guard._deny('unsupported_window_target')
            guard.emit('p04h_roster_open', vehicle=vehicle, slot=int(ctx['data']['slot']), original_callback_called=True)
            return original(owner, event)
        return open_window

    def _window_ok(self, window):
        return (type(window._currentVehicleInvId) in recruitment.integer_types
                and window._currentVehicleInvId in VEHICLES and window._menuEnabled is False
                and target_matches(window._initData, window._currentVehicleInvId))

    def _mask(self, window, state):
        flash = window.flashObject
        if flash is None:
            raise RuntimeError('original recruitment window is not Flash-bound')
        for button in (flash.btnAcademy, flash.btnScool):
            button.visible, button.enabled, button.type = False, False, 'free'
            button.validateNow()
        free = flash.btnCourses
        free.type = 'free'
        free.validateNow()
        free.visible, free.selected, free.typeSwitcher.visible = True, True, False
        free.enabled = state['free_quota'] > 0 and len(state['tankmen']) < MAX_TANKMEN and not self.submitted
        free.typeLabel.text = LABEL % state['free_quota']
        flash.btnRecruit.enabled = free.enabled
        for name in ('nationDropdown', 'vehicleClassDropdown', 'vehicleTypeDropdown', 'roleDropdown'):
            getattr(flash, name).enabled = False

    def _initial(self, original):
        guard = self
        def initial(window):
            state = guard._state()
            if not guard._window_ok(window) or window._currentVehicleInvId != state['selected_inventory_id']:
                raise RuntimeError('unsupported roster window initialization')
            if guard.window is not window:
                if window in guard.windows or len(guard.windows) >= 32:
                    raise RuntimeError('roster dialog reuse or instance budget exceeded')
                guard.windows.append(window)
                guard.window, guard.submitted = window, False
            guard._mask(window, state)
            window.flashObject.as_initData(dict(credits=state['credits'], gold=state['gold'],
                data=target_data(window._currentVehicleInvId, int(window._initData['slot'])),
                menuEnabled=False, schoolUpgradeActionPriceData=None, academyUpgradeActionPriceData=None))
            window.flashObject.validateNow()
            guard._mask(window, state)
            guard.emit('p04h_roster_window_ready', vehicle=window._currentVehicleInvId,
                       slot=int(window._initData['slot']), free_quota=state['free_quota'],
                       role_level=ROLE_LEVEL, paid_controls_hidden=True, original_window_title_preserved=True)
        return initial

    def _buy(self, original):
        guard = self
        def buy(window, nationID, vehTypeID, role, studyType, slot):
            state = guard._state()
            if (not guard._window_ok(window) or window is not guard.window
                    or window._currentVehicleInvId != state['selected_inventory_id']
                    or not recruitment._number_equals(nationID, 0)
                    or not recruitment._number_equals(vehTypeID, VEHICLES[window._currentVehicleInvId][1])
                    or not recruitment._number_equals(studyType, 0)
                    or not recruitment._number_equals(slot, window._initData['slot'])
                    or role != window._initData['roleType']):
                return guard._deny('unsupported_recruit_target_or_tariff')
            if state['free_quota'] == 0 or len(state['tankmen']) >= MAX_TANKMEN or guard.submitted:
                return guard._deny('quota_capacity_or_dialog_submission_exhausted')
            guard.submitted = True
            guard._mask(window, state)
            guard.emit('p04h_roster_submit', vehicle=window._currentVehicleInvId, slot=int(slot),
                       tariff=0, role_level=ROLE_LEVEL, original_callback_called=True,
                       original_processor='TankmanRecruitAndEquip', native_cmd=309)
            return original(window, nationID, vehTypeID, role, studyType, slot)
        return buy


class _RosterTransferGuard(transfer._TransferGuard):
    def __init__(self, classes, messages, record, snapshot=None):
        transfer._TransferGuard.__init__(self, classes, messages, record,
                                        native_snapshot if snapshot is None else snapshot)

    def emit(self, event, **fields):
        if self.events >= 2048 and not event.endswith('_policy'):
            raise RuntimeError('roster transfer event budget exhausted')
        self.events += 1
        fields.update(version=VERSION, policy=POLICY)
        self.record(event.replace('p04f_transfer', 'p04h_transfer'), **fields)

    def _deny(self, callback):
        self.emit('p04h_transfer_denied', callback=callback, original_callback_called=False)
        if self.messages.g_instance is None:
            raise RuntimeError('original SystemMessages unavailable')
        self.messages.pushMessage(NOTICE, type=self.messages.SM_TYPE.Warning)

    def _wrapper(self, original, callback, name, static):
        guard = self
        def wrapped(*args, **kwargs):
            if not guard.active:
                raise RuntimeError('roster callback after cleanup')
            supplied = args if static else args[1:]
            try:
                if kwargs or not static and not args:
                    raise ValueError('original positional callback required')
                state = checked_expected(guard.snapshot(), ROLE_LEVEL)
                vehicle = state['selected_inventory_id']
                if name == 'equipTankman':
                    if len(supplied) != 2:
                        raise ValueError('equip callback arity')
                    identity = callback_integer(supplied[0], 1, len(state['tankmen']))
                    slot = callback_integer(supplied[1], 0, len(VEHICLES[vehicle][3]) - 1)
                    projected_transfer(state, vehicle, slot, identity)
                elif name == 'unloadTankman':
                    if len(supplied) != 1:
                        raise ValueError('unload callback arity')
                    member = state['tankmen'][callback_integer(supplied[0], 1, len(state['tankmen'])) - 1]
                    if callback == 'Barracks.unloadTankman':
                        vehicle = member['vehicle_inventory_id']
                    if vehicle not in VEHICLES or member['vehicle_inventory_id'] != vehicle:
                        raise ValueError('tankman is not seated in the original target')
                    slot, identity = member['slot'], -1
                else:
                    if supplied or all(item is None for item in state[crew_key(vehicle)]):
                        raise ValueError('whole crew unload requires occupied seats')
                    slot, identity = -1, -1
            except ValueError:
                return guard._deny(callback)
            guard.emit('p04h_transfer_ui_call', callback=callback, vehicle=vehicle, slot=slot,
                       tankman_id=identity, native_cmd=105, original_callback_called=True)
            return original(*args, **kwargs)
        return wrapped


def init(record):
    global _recruit_guard, _transfer_guard, _record
    import crew_capabilities
    from gui.Scaleform.daapi.business_layer import BusinessHandler
    from gui.Scaleform.daapi.view.lobby.recruitWindow.RecruitWindow import RecruitWindow
    from gui.Scaleform.daapi.view.lobby.hangar.Crew import Crew
    from gui.Scaleform.daapi.view.lobby.barracks.Barracks import Barracks
    from gui import SystemMessages
    capability = crew_capabilities._guard
    if (_recruit_guard is not None or _transfer_guard is not None or recruitment._guard is not None
            or transfer._guard is not None or cross._guard is not None or capability is None
            or not capability.active or getattr(capability, 'allow_roster', False) is not True):
        raise RuntimeError('explicit exclusive roster capability required')
    classes = dict(Crew=Crew, Barracks=Barracks)
    targets = [(classes[a], b) for a, b, _ in transfer.TARGETS] + [
        (BusinessHandler, '_BusinessHandler__showRecruitWindow'), (RecruitWindow, 'buyTankman')]
    if any((row[0], row[1]) in targets for row in capability.bindings):
        raise RuntimeError('roster callbacks remain blocked by capability guard')
    recruit = _RosterRecruitGuard(BusinessHandler, RecruitWindow, SystemMessages, record)
    moving = _RosterTransferGuard(classes, SystemMessages, record)
    recruit.install()
    try:
        moving.install()
    except Exception:
        recruit.restore()
        raise
    _recruit_guard, _transfer_guard, _record = recruit, moving, record


def fini():
    global _recruit_guard, _transfer_guard, _scenario, _record
    if _transfer_guard is not None:
        _transfer_guard.restore()
        _transfer_guard = None
    if _recruit_guard is not None:
        _recruit_guard.restore()
        _recruit_guard = None
    _scenario, _record = None, None


def observe_profile(frame, phase):
    if _record is None:
        return
    fields = command_observation(frame, phase)
    if fields is not None:
        _record('p04h_native_roster_request', **fields)


def native_event(fields):
    if _scenario is not None and _scenario.pending is not None:
        try:
            _scenario.pending['tracker'].observe(fields)
        except (ValueError, KeyError, TypeError) as error:
            _scenario.error = str(error)


def native_window_evidence(window, snapshot):
    flash = window.flashObject
    if flash is None or _recruit_guard is None or not _recruit_guard._window_ok(window):
        raise RuntimeError('source-bound original recruitment window required')
    for name in ('btnAcademy', 'btnScool'):
        button = getattr(flash, name)
        if button.visible is not False or button.enabled is not False or button.type != 'free':
            raise RuntimeError('paid roster controls must remain unavailable')
    free = flash.btnCourses
    if (free.visible is not True or free.enabled is not True or free.type != 'free'
            or free.typeSwitcher.visible is not False or free.typeLabel.text != LABEL % snapshot['free_quota']
            or flash.btnRecruit.enabled is not True):
        raise RuntimeError('original roster window policy/quota label differs')
    return dict(vehicle=window._currentVehicleInvId, slot=int(window._initData['slot']),
                role=window._initData['roleType'], role_level=ROLE_LEVEL, tariff=0,
                free_quota=snapshot['free_quota'], label=free.typeLabel.text,
                paid_controls_hidden=True, original_window_title_preserved=True,
                observation='PyGFx properties; actual pixels are separate evidence')


class _Screenshots(recruitment._Screenshots):
    def capture(self, name, record):
        allowed = ['p04h_roster_initial', 'p04h_roster_relogin_ms1', 'p04h_roster_relogin_is7']
        allowed += ['p04h_' + step[0] for step in STEPS]
        allowed += ['p04h_window_' + step[0] for step in STEPS[:7]]
        if name not in allowed:
            raise ValueError('unsupported roster screenshot basename')
        if name not in self.requested:
            if any(entry.startswith(name + '_') for entry in self._entries()):
                raise ValueError('roster screenshot basename occupied')
            import BigWorld
            self.requested.add(name)
            BigWorld.screenShot('png', name)
            record('p04h_roster_screenshot_requested', basename=name, writer='BigWorld.screenShot')
        names = [entry for entry in self._entries() if re.match(r'\A' + re.escape(name) + r'_[0-9]{3,10}\.png\Z', entry)]
        if not names:
            return None
        if len(names) != 1:
            raise ValueError('ambiguous native roster screenshot')
        from project_preferences import owned
        from ms1_crew_scenario import png_evidence
        path = owned(os.path.join(self.directory, names[0]), self.directory)
        if not os.path.isfile(path) or os.path.islink(path):
            raise ValueError('native roster screenshot must be owned regular file')
        return png_evidence(path, name)


class NativeScenario(transfer.NativeScenario):
    def __init__(self, record, mode, expected, hires=None, settings=None, clock=None):
        global _scenario
        if not callable(record) or mode not in ('recruit', 'relogin'):
            raise ValueError('explicit native roster diagnostic mode required')
        self.expected = checked_expected(expected, ROLE_LEVEL)
        self.hires = checked_hires(hires) if mode == 'recruit' else None
        if mode == 'relogin' and hires is not None:
            raise ValueError('read-only relogin cannot carry hire catalog')
        if mode == 'recruit' and (len(self.expected['tankmen']) != 3 or self.expected['free_quota'] != 13
                or self.expected['ms1_crew'] != [None, 2] or self.expected['is7_crew'] != [1, None, None, None, None]):
            raise ValueError('roster diagnostic starts from accepted G with explicit capacity16 quota grant')
        if mode == 'relogin' and (len(self.expected['tankmen']) != 10 or self.expected['free_quota'] != 6
                or self.expected['ms1_crew'] != [4, 5] or self.expected['is7_crew'] != [6, 7, 8, 10, 9]):
            raise ValueError('roster relogin requires completed ten-operation snapshot')
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
            raise RuntimeError('only one active roster diagnostic permitted')
        _scenario = self

    def emit(self, event, **fields):
        fields.update(version=VERSION, policy=POLICY, step=self.step)
        if 'snapshot' in fields:
            fields.update(native_descriptor_parse_repack=True,
                          native_descriptor_count=len(fields['snapshot']['tankmen']),
                          separate_dossier_parse_repack='NOT_RUN')
        self.record(event, **fields)

    def _select(self, page, vehicle, following):
        self.selected, self.after_selection, self.selection_ready = vehicle, following, None
        self.phase = 'wait_selection'
        page.tankCarousel.vehicleChange(vehicle)
        self.emit('p04h_roster_select', vehicle=vehicle, original_callback='TankCarousel.vehicleChange')

    def _capture(self, name):
        if self.last_time - self.ready_since > 20:
            raise RuntimeError('native roster screenshot deadline20s exceeded')
        if self.last_time - self.ready_since < 2:
            return False
        capture = None if self.screenshots is None else self.screenshots.capture(name, self.record)
        if self.screenshots is not None and capture is None:
            return False
        if capture is not None:
            self.captures.append(capture)
            self.emit('p04h_roster_screenshot', screenshot=capture, vehicle=self.selected)
        return True

    def _advance(self, ready):
        if not ready:
            self.selection_ready = None
            return False
        from gui.WindowsManager import g_windowsManager
        from gui.Scaleform.framework import ViewTypes
        from gui.Scaleform.Waiting import Waiting
        from gui.Scaleform.daapi.settings.views import VIEW_ALIAS
        from gui.Scaleform.framework.managers.containers import POP_UP_CRITERIA
        from CurrentVehicle import g_currentVehicle
        manager = g_windowsManager.window.containerManager
        page = manager.getContainer(ViewTypes.LOBBY_SUB).getView()
        if type(page).__name__ != 'Hangar' or page.flashObject is None or page.crewPanel.flashObject is None:
            raise RuntimeError('original Flash-bound Hangar and Crew required')
        if Waiting.isVisible():
            self.selection_ready = None
            return False
        window = manager.getContainer(ViewTypes.WINDOW).getView(
            criteria={POP_UP_CRITERIA.VIEW_ALIAS: VIEW_ALIAS.RECRUIT_WINDOW})
        if self.phase == 'wait_hangar':
            self._select(page, 1 if self.mode == 'recruit' else 3 - self.expected['selected_inventory_id'], 'initial_capture')
            return False
        if g_currentVehicle.invID != self.selected:
            if self.phase == 'wait_selection':
                self.selection_ready = None
                return False
            raise RuntimeError('native selected vehicle changed during roster diagnostic')
        if self.phase == 'wait_selection':
            if self.selection_ready is None:
                self.selection_ready = self.last_time
            if self.last_time - self.selection_ready < 2:
                return False
            actual, ammo = native_snapshot(ROLE_LEVEL), cross.native_ammunition()
            expected = dict(self.expected if self.snapshot is None else self.snapshot, selected_inventory_id=self.selected)
            if actual != expected or self.ammo is not None and ammo != self.ammo:
                raise RuntimeError('native selection changed roster or ammunition')
            self.snapshot, self.ammo = actual, ammo
            self.phase, self.ready_since = self.after_selection, self.last_time
            if self.phase == 'initial_capture':
                self.emit('p04h_roster_initial', snapshot=actual, ammunition=ammo,
                          efficiency=native_efficiency(actual), readiness=native_readiness(actual))
        if self.phase in ('initial_capture', 'after_capture', 'relogin_capture'):
            if window is not None:
                return False
            if native_snapshot(ROLE_LEVEL) != self.snapshot or cross.native_ammunition() != self.ammo:
                raise RuntimeError('native roster changed during rendered evidence')
            name = ('p04h_roster_relogin_' + ('ms1' if self.selected == 1 else 'is7') if self.mode == 'relogin'
                    else 'p04h_roster_initial' if self.phase == 'initial_capture' else 'p04h_' + STEPS[self.step][0])
            if not self._capture(name):
                return False
            efficiency, readiness = native_efficiency(self.snapshot), native_readiness(self.snapshot)
            if self.mode == 'relogin':
                self.relogin_views.append(self.selected)
                self.emit('p04h_roster_relogin_view', vehicle=self.selected, snapshot=self.snapshot,
                          efficiency=efficiency, readiness=readiness)
                if len(self.relogin_views) == 1:
                    self._select(page, self.expected['selected_inventory_id'], 'relogin_capture')
                    return False
                if self.snapshot != self.expected or set(self.relogin_views) != set((1, 2)):
                    raise RuntimeError('fresh login did not preserve both full native crews')
                self.emit('p04h_roster_relogin', snapshot=self.snapshot, ammunition=self.ammo,
                          efficiency=efficiency, readiness=readiness, exact_snapshot_match=True,
                          vehicles_observed=self.relogin_views, action='read_only')
                self.phase = 'complete'
                return True
            if self.phase == 'after_capture':
                self.step += 1
                self.pending = None
            if self.step == len(STEPS):
                self.emit('p04h_roster_final', snapshot=self.snapshot, ammunition=self.ammo,
                          efficiency=efficiency, readiness=readiness, operations=10,
                          hires=7, transfers=3, physical_pointer_input=False, pixels='NOT_RUN')
                self.phase = 'complete'
                return True
            if STEPS[self.step][1] != self.selected:
                self._select(page, STEPS[self.step][1], 'action')
                return False
            self.phase = 'action'
        if self.phase == 'action':
            name, vehicle, callback, args, slot, identity = STEPS[self.step]
            if vehicle != self.selected or native_snapshot(ROLE_LEVEL) != self.snapshot or window is not None:
                raise RuntimeError('native roster callback target/state/window changed')
            self.emit('p04h_roster_before', name=name, snapshot=self.snapshot, ammunition=self.ammo,
                      efficiency=native_efficiency(self.snapshot), readiness=native_readiness(self.snapshot))
            command = 309 if self.step < len(HIRES) else 105
            layout = [3, vehicle, slot, 0] if command == 309 else [vehicle, slot, identity]
            expected = (projected_recruit(self.snapshot, self.hires[self.step]) if command == 309
                        else projected_transfer(self.snapshot, vehicle, slot, identity))
            self.pending = dict(tracker=NativeCommandTracker(command, layout), expected=expected)
            if command == 309:
                if _recruit_guard is None or not _recruit_guard.active:
                    raise RuntimeError('active original roster recruitment guard required')
                self.phase = 'wait_window'
                page.crewPanel.onShowRecruitWindowClick(target_data(vehicle, slot), False)
            else:
                self.phase = 'wait_result'
                self.emit('p04h_roster_action', name=name, original_callback='Crew.' + callback,
                          arguments=list(args), native_cmd=command, layout=layout)
                getattr(page.crewPanel, callback)(*args)
            return False
        if self.phase in ('wait_window', 'window_ready'):
            if window is None or window.flashObject is None:
                return False
            if type(window) is not _recruit_guard.window_class or not _recruit_guard._window_ok(window):
                raise RuntimeError('unexpected original roster recruitment window')
            if native_snapshot(ROLE_LEVEL) != self.snapshot or cross.native_ammunition() != self.ammo:
                raise RuntimeError('native account changed before original recruitment submission')
            observation = native_window_evidence(window, self.snapshot)
            if self.phase == 'wait_window':
                self.emit('p04h_roster_window_observed', name=STEPS[self.step][0], observation=observation)
                self.phase, self.ready_since = 'window_ready', self.last_time
                return False
            if not self._capture('p04h_window_' + STEPS[self.step][0]):
                return False
            vehicle, slot, role = HIRES[self.step]
            args = [0, VEHICLES[vehicle][1], role, 0, slot]
            self.phase = 'wait_result'
            self.emit('p04h_roster_action', name=STEPS[self.step][0], original_callback='RecruitWindow.buyTankman',
                      arguments=args, native_cmd=309, layout=self.pending['tracker'].layout)
            window.buyTankman(*args)
            return False
        if self.phase == 'wait_result':
            tracker = self.pending['tracker']
            if tracker.success is None:
                return False
            actual, ammo = native_snapshot(ROLE_LEVEL), cross.native_ammunition()
            if actual != self.pending['expected'] or ammo != self.ammo:
                raise RuntimeError('native roster/descriptor/quota/resources/ammunition differs from exact expected transition')
            self.snapshot = actual
            self.emit('p04h_roster_callback', **tracker.receipt())
            self.emit('p04h_roster_after', name=STEPS[self.step][0], snapshot=actual, ammunition=ammo,
                      efficiency=native_efficiency(actual), readiness=native_readiness(actual), action='native_inventory_readback')
            self.phase, self.ready_since = 'after_capture', self.last_time
        return False
