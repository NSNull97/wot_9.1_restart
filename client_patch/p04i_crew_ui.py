# -*- coding: utf-8 -*-
"""Original #717 PersonalCase, first-skill UI and passive command readback.

Unavailable tariff tabs have no model. Original common/dossier/skill readers
and native processors remain authoritative consumers of server-owned state.
Expected snapshot projections below modify evidence copies, never GUI caches.
"""
import copy
import binascii
import hashlib
import math
import re
import os
import time

import crew_vehicles
import p04d_crew_ui as recruitment
import p04f_crew_ui as transfer
import p04g_crew_ui as cross
import p04h_crew_ui as roster

VERSION = 1
POLICY = 'test_lab.ms1_is7.progression.first_skill0.base_sixth.v1'
ROLE_LEVEL = 50
NOTICE = u'Навык доступен при 100% основной специальности. Шестое чувство — базовое; боевой сигнал ещё не подключён. Обучение, сброс, документы и увольнение недоступны.'
BASE_NOTICE = u'Шестое чувство: базовое, независимо от обучения. Боевой сигнал — следующий этап.'
MAX_TANKMEN = 16
VEHICLES = {
    1: (3329, 13, 'lightTank', ('commander', 'driver')),
    2: (7169, 28, 'heavyTank', ('commander', 'gunner', 'driver', 'loader', 'loader')),
}
ROW_FIELDS = (roster.ROW_FIELDS - set(('no_skills',))) | set(('skills', 'last_skill_level', 'dossier_bytes', 'dossier_sha256'))
SNAPSHOT_FIELDS = roster.SNAPSHOT_FIELDS
DOSSIER = b'\x42\x00\x00\x00\x00\x00'
DOSSIER_SHA256 = hashlib.sha256(DOSSIER).hexdigest()
EXCLUDED_SKILLS = ('commander_sixthSense', 'gunner_woodHunter')
SKILL_IDS = {'repair': 6, 'fireFighting': 7, 'camouflage': 8, 'brotherhood': 9,
 'commander_tutor': 16, 'commander_eagleEye': 17, 'commander_expert': 19, 'commander_universalist': 20,
 'driver_virtuoso': 28, 'driver_smoothDriving': 29, 'driver_badRoadsKing': 30, 'driver_rammingMaster': 31, 'driver_tidyPerson': 32,
 'gunner_gunsmith': 37, 'gunner_sniper': 38, 'gunner_smoothTurret': 39, 'gunner_rancorous': 40,
 'loader_pedant': 46, 'loader_desperado': 47, 'loader_intuition': 48,
 'radioman_inventor': 53, 'radioman_finder': 54, 'radioman_retransmitter': 55, 'radioman_lastEffort': 56}
COMBINED_ROLES = {1: (('commander', 'gunner', 'radioman', 'loader'), ('driver',)),
 2: (('commander',), ('gunner',), ('driver',), ('loader',), ('loader', 'radioman'))}
COMMAND_PIN = (1523, 'efb40e1d1742e98179a41a6d907f06ec749d64f1e6419c414fe702535f42ec36')
LEARNING = ((1, 'commander_tutor', 16), (2, 'driver_smoothDriving', 29), (3, 'repair', 6))
STEPS = (('seat_commander', 105, [1, 0, 1]), ('learn_commander', 151, [1, 16, 0]),
 ('unload_commander', 105, [1, 0, -1]), ('restore_commander4', 105, [1, 0, 4]),
 ('learn_driver2', 151, [2, 29, 0]), ('learn_driver3', 151, [3, 6, 0]))
_recruit_guard = None
_transfer_guard = None
_personal_guard = None
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
    if crew_vehicles.enabled():
        raise RuntimeError('CREW-ANY serves the P04J/P04K roster only')
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
                or type(row['skills']) is not list or len(row['skills']) > 1
                or any(skill not in SKILL_IDS for skill in row['skills'])):
            raise ValueError('native descriptor hash and empty skills required')
        integer(row['free_xp'], 0, 0)
        integer(row['last_skill_level'], 0, 0)
        integer(row['dossier_bytes'], 6, 6)
        if row['dossier_sha256'] != DOSSIER_SHA256 or row['skills'] and row['role_level'] != 100:
            raise ValueError('preserved empty dossier and qualified skills required')
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
                    or row['role_level'] != 100 or not row['skills'] and row['sha256'] != pin):
                raise ValueError('accepted original tankman descriptor changed')
        elif role_level is not None and row['role_level'] != role_level:
            raise ValueError('new tankman level differs from selected policy')
    if set(seats) - set(range(1, len(members) + 1)):
        raise ValueError('vehicle references an absent native tankman')
    return copy.deepcopy(value)


def native_snapshot(role_level=None):
    if crew_vehicles.enabled():
        raise RuntimeError('CREW-ANY serves the P04J/P04K roster only')
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
        if (not isinstance(compact, bytes) or not 25 <= len(compact) <= 26
                or desc.makeCompactDescr() != compact or item.invID != identity):
            raise ValueError('original descriptor parse/repack or identity differs')
        rows.append(dict(inventory_id=identity, vehicle_inventory_id=item.vehicleInvID,
                         slot=item.vehicleSlotIdx, sha256=hashlib.sha256(compact).hexdigest(),
                         nation_id=desc.nationID, vehicle_type_id=desc.vehicleTypeID,
                         role=desc.role, role_level=desc.roleLevel,
                         skills=list(desc.skills), last_skill_level=desc.lastSkillLevel, free_xp=desc.freeXP,
                         dossier_bytes=len(desc.dossierCompactDescr),
                         dossier_sha256=hashlib.sha256(desc.dossierCompactDescr).hexdigest()))
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
            or code.co_name != '__doCmd' or values.get('cmd') not in (105, 151)):
        return None
    if (code.co_firstlineno, hashlib.sha256(code.co_code).hexdigest()) != COMMAND_PIN:
        raise RuntimeError('original roster command observer source differs')
    command, args = values['cmd'], values.get('args')
    if type(args) is not tuple or len(args) != (3):
        raise ValueError('original roster command argument shape differs')
    if command == 151:
        layout = [integer(args[0], 1, MAX_TANKMEN), integer(args[1], 1, 63), integer(args[2], 0, 0)]
        if layout[1] not in SKILL_IDS.values():
            raise ValueError('unsupported native skill index')
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
        if command not in (105, 151) or type(layout) is not list or len(layout) != (3):
            raise ValueError('one explicit roster command layout required')
        self.command, self.layout = command, list(layout)
        self.request, self.update, self.success = None, None, None

    def observe(self, fields):
        event = fields.get('event')
        if event == 'p04i_native_progression_request':
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
    if isinstance(value, recruitment.string_types) and re.match(r'\A[0-9]{1,%d}\Z' % crew_vehicles.digits(), value):
        return integer(int(value), low, high)
    raise ValueError('native callback integer required')


def _assignments(value):
    if crew_vehicles.enabled():
        return crew_vehicles.assignments(value)
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


def combined_roles(row):
    return ((row['role'],) if row['vehicle_inventory_id'] == -1 else
            crew_vehicles.combined(COMBINED_ROLES, row['vehicle_inventory_id'], row['slot']))


def eligible_names(row):
    return sorted(name for name in SKILL_IDS if name not in row['skills'] and
                  ('_' not in name or name.split('_', 1)[0] in combined_roles(row)))


def checked_learning(rows):
    if type(rows) is not list or len(rows) != 3:
        raise ValueError('three exact learned descriptor rows required')
    for row, (identity, name, index) in zip(rows, LEARNING):
        if type(row) is not dict or set(row) != ROW_FIELDS:
            raise ValueError('exact learned descriptor row required')
        for key, low, high in (('inventory_id', 1, 3), ('role_level', 100, 100), ('last_skill_level', 0, 0), ('free_xp', 0, 0), ('dossier_bytes', 6, 6)):
            integer(row[key], low, high)
        if (type(row) is not dict or set(row) != ROW_FIELDS or row['inventory_id'] != identity
                or row['skills'] != [name] or row['last_skill_level'] != 0 or row['free_xp'] != 0
                or row['role_level'] != 100 or row['dossier_bytes'] != 6
                or row['dossier_sha256'] != DOSSIER_SHA256
                or not isinstance(row['sha256'], recruitment.string_types)
                or re.match(r'\A[0-9a-f]{64}\Z', row['sha256']) is None):
            raise ValueError('learned descriptor row differs from explicit first-skill contract')
    return copy.deepcopy(rows)


def projected_learning(snapshot, learned):
    value = checked_expected(snapshot, ROLE_LEVEL)
    identity = integer(learned['inventory_id'], 1, len(value['tankmen']))
    row = value['tankmen'][identity - 1]
    allowed = ('skills', 'last_skill_level', 'sha256', 'vehicle_inventory_id', 'slot')
    if (row['skills'] or row['role_level'] != 100 or len(learned['skills']) != 1
            or learned['skills'][0] not in eligible_names(row)
            or any(learned[key] != row[key] for key in ROW_FIELDS - set(allowed))):
        raise ValueError('skill selection changed immutable native descriptor fields or eligibility')
    row.update(skills=list(learned['skills']), last_skill_level=learned['last_skill_level'], sha256=learned['sha256'])
    return checked_expected(value, ROLE_LEVEL)


class _Native(object):
    def state(self):
        return native_snapshot(ROLE_LEVEL)


class _RecruitGuard(roster._RosterRecruitGuard):
    def _state(self):
        if not self.active:
            raise RuntimeError('progression recruitment after cleanup')
        return checked_expected(self.native.state(), ROLE_LEVEL)

    def _deny(self, reason):
        self.emit('p04i_recruit_denied', reason=reason, original_callback_called=False)
        self.messages.pushMessage(NOTICE, type=self.messages.SM_TYPE.Warning)


def personal_tab_count(flash):
    """PyGFx converts the original DataProvider to a Python list in #717.

    Native01 observed this at PersonalCase.getCommonData. Keep the bounded
    Flash-object representation for callers retaining an object proxy.
    """
    provider = flash.tabs.dataProvider
    count = len(provider) if type(provider) is list else roster.callback_integer(provider.length, 1, 4)
    if count not in (1, 4):
        raise RuntimeError('source-bound PersonalCase tab count differs')
    return count


class _PersonalGuard(object):
    """Narrow UI capability adapter, retaining original data and command paths.

    #717 Application configUI requests every tab unconditionally. The two
    unavailable tariff setters remain null; runtimeUpdateByInstance explicitly
    skips their null models. No price, tariff or successful result is supplied.
    """
    def __init__(self, window_class, meta_class, messages, record, snapshot=None, member=None, business_class=None):
        self.window_class, self.meta_class = window_class, meta_class
        self.business_class = business_class
        self.messages, self.record = messages, record
        self.snapshot = native_snapshot if snapshot is None else snapshot
        self.member = self._native_member if member is None else member
        self.active, self.bindings = False, []
        self.windows, self.models, self.notified = [], {}, set()

    @staticmethod
    def _native_member(identity):
        from gui.shared import g_itemsCache
        return g_itemsCache.items.getTankman(identity)

    def _row(self, window):
        if not self.active:
            raise RuntimeError('personal case callback after cleanup')
        state = checked_expected(self.snapshot(), ROLE_LEVEL)
        identity = integer(window.tmanInvID, 1, len(state['tankmen']))
        item = self.member(identity)
        row = state['tankmen'][identity - 1]
        if item is None or item.invID != identity or tuple(item.combinedRoles) != combined_roles(row):
            raise ValueError('original personal case member or combined roles differs')
        if window not in self.windows:
            if len(self.windows) >= 32:
                raise RuntimeError('personal case instance budget exceeded')
            self.windows.append(window)
        self.models.setdefault(window, {})
        return row, item

    def mask(self, window):
        row, item = self._row(window)
        flash = window.flashObject
        if flash is None:
            raise RuntimeError('original PersonalCase Flash object required')
        flash.validateNow()
        flash.tabs.validateNow()
        count = personal_tab_count(flash)
        if count == 4:
            for index in (1, 3):
                button = flash.tabs.getButtonAt(index)
                if button is None:
                    raise RuntimeError('original tab renderer absent after validation')
                button.enabled = False
                button.validateNow()
        for name in ('unloadBtn', 'dismissBtn', 'dropSkillsButton', 'accTeachingOfSkillBtn'):
            button = getattr(flash, name)
            button.enabled, button.visible = False, False
        if row['role_level'] < 100:
            flash.skillsBtn.enabled = False
        if window not in self.notified:
            if self.messages.g_instance is None:
                raise RuntimeError('original SystemMessages required for base capability notice')
            self.messages.pushMessage(BASE_NOTICE, type=self.messages.SM_TYPE.Warning)
            self.notified.add(window)
            self.record('p04i_base_capability_notice', inventory_id=row['inventory_id'], text=BASE_NOTICE,
                        capability='sixth_sense', base=True, qualification_independent=True,
                        descriptor_skill=False, combat_signal='NOT_IMPLEMENTED')

    def _unavailable(self, name):
        guard = self
        def disabled(window):
            guard._row(window)
            guard.record('p04i_personal_unavailable', inventory_id=window.tmanInvID,
                         callback=name, original_called=False, supplied_model=False)
        return disabled

    def _open(self, original):
        guard = self
        def open_window(owner, event):
            if not guard.active:
                raise RuntimeError('personal case entry after cleanup')
            state, ctx = checked_expected(guard.snapshot(), ROLE_LEVEL), event.ctx
            if (type(ctx) is not dict or set(ctx) - set(('tankmanID', 'page'))
                    or type(ctx.get('tankmanID')) not in recruitment.integer_types
                    or not 1 <= ctx['tankmanID'] <= len(state['tankmen'])
                    or type(ctx.get('page', -1)) not in recruitment.integer_types
                    or ctx.get('page', -1) not in (-1, 0, 2)):
                guard.record('p04i_personal_denied', action='open_unsupported_page', original_called=False)
                guard.messages.pushMessage(NOTICE, type=guard.messages.SM_TYPE.Warning)
                return
            return original(owner, event)
        return open_window

    def _data(self, original, kind):
        guard = self
        def data(window, value):
            row, item = guard._row(window)
            if kind == 'skills':
                if type(value) is not list or not 1 <= len(value) <= 6:
                    raise ValueError('original skill group shape differs')
                result, catalog = [], []
                for group in value:
                    if type(group) is not dict or set(group) != set(('id', 'skills')) or type(group['skills']) is not list:
                        raise ValueError('original skill group schema differs')
                    rows = []
                    for skill in group['skills']:
                        if (type(skill) is not dict or set(skill) != set(('id', 'name', 'desc', 'enabled', 'tankmanID', 'tooltip'))
                                or skill['tankmanID'] != row['inventory_id']):
                            raise ValueError('original skill VO schema or member differs')
                        if skill['id'] in EXCLUDED_SKILLS:
                            continue
                        if skill['id'] not in eligible_names(row) or len(catalog) >= 32:
                            raise ValueError('original skill list differs from current combined roles')
                        copied = dict(skill)
                        copied['enabled'] = bool(skill['enabled'] and item.hasNewSkill and row['role_level'] == 100)
                        rows.append(copied)
                        catalog.append(skill['id'])
                    result.append(dict(id=group['id'], skills=rows))
                if sorted(catalog) != eligible_names(row):
                    raise ValueError('original catalog missing or duplicated source skill')
                value = result
                guard.models[window]['catalog'] = sorted(catalog)
                guard.models[window]['can_learn'] = bool(item.hasNewSkill and row['role_level'] == 100)
                guard.record('p04i_personal_catalog', inventory_id=row['inventory_id'], catalog=sorted(catalog),
                             combined_roles=list(item.combinedRoles), has_new_skill=bool(item.hasNewSkill),
                             qualification=row['role_level'], excluded=list(EXCLUDED_SKILLS))
            elif type(value) is not dict:
                raise ValueError('original personal case data model required')
            guard.models[window][kind] = copy.deepcopy(value)
            result = original(window, value)
            if kind == 'common':
                guard.mask(window)
            return result
        return data

    def _learn(self, original):
        guard = self
        def learn(window, identity, name):
            row, item = guard._row(window)
            model = guard.models[window]
            if (roster.callback_integer(identity, 1, crew_vehicles.max_tankmen(MAX_TANKMEN)) != row['inventory_id']
                    or name not in model.get('catalog', ()) or name not in eligible_names(row)
                    or row['role_level'] != 100 or row['skills'] or not item.hasNewSkill
                    or model.get('submitted') or name in EXCLUDED_SKILLS):
                guard.record('p04i_personal_denied', inventory_id=row['inventory_id'], action='learn', original_called=False)
                guard.messages.pushMessage(NOTICE, type=guard.messages.SM_TYPE.Warning)
                return
            model['submitted'] = True
            guard.record('p04i_personal_submit', inventory_id=row['inventory_id'], skill=name,
                         native_cmd=151, layout=[row['inventory_id'], SKILL_IDS[name], 0], original_called=True)
            return original(window, identity, name)
        return learn

    def install(self):
        if self.active:
            raise RuntimeError('personal guard already installed')
        cls, meta = self.window_class, self.meta_class
        if self.business_class is not None:
            original = self.business_class.__dict__['showCrewTankmanInfo']
            self.bindings.append((self.business_class, 'showCrewTankmanInfo', original, self._open(original)))
        for name in ('_PersonalCase__setRetrainingData', '_PersonalCase__setDocumentsData'):
            self.bindings.append((cls, name, cls.__dict__[name], self._unavailable(name)))
        self.bindings.append((cls, 'addTankmanSkill', cls.__dict__['addTankmanSkill'], self._learn(cls.__dict__['addTankmanSkill'])))
        for name, kind in (('as_setCommonDataS', 'common'), ('as_setSkillsDataS', 'skills'), ('as_setDossierDataS', 'dossier')):
            original = meta.__dict__[name]
            self.bindings.append((meta, name, original, self._data(original, kind)))
        for target, name, original, replacement in self.bindings:
            if target.__dict__.get(name) is not original:
                raise RuntimeError('personal callback changed before install')
        for target, name, original, replacement in self.bindings:
            setattr(target, name, replacement)
        self.active = True
        self.record('p04i_personal_policy', phase='install', original_common_dossier_skills=True,
                    unavailable_tabs=[1, 3], null_models_preserved=True, base_sixth=True)

    def restore(self):
        if not self.active:
            return
        for target, name, original, replacement in self.bindings:
            if target.__dict__.get(name) is not replacement:
                raise RuntimeError('personal callback changed during cleanup')
        for target, name, original, replacement in self.bindings:
            setattr(target, name, original)
        self.active = False
        self.record('p04i_personal_policy', phase='restore', original_binding_restored=True)


class _TransferGuard(transfer._TransferGuard):
    def __init__(self, classes, messages, record, snapshot=None):
        transfer._TransferGuard.__init__(self, classes, messages, record,
                                        native_snapshot if snapshot is None else snapshot)

    def emit(self, event, **fields):
        if self.events >= 2048 and not event.endswith('_policy'):
            raise RuntimeError('roster transfer event budget exhausted')
        self.events += 1
        fields.update(version=VERSION, policy=POLICY)
        self.record(event.replace('p04f_transfer', 'p04i_transfer'), **fields)

    def _deny(self, callback):
        self.emit('p04i_transfer_denied', callback=callback, original_callback_called=False)
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
            guard.emit('p04i_transfer_ui_call', callback=callback, vehicle=vehicle, slot=slot,
                       tankman_id=identity, native_cmd=105, original_callback_called=True)
            return original(*args, **kwargs)
        return wrapped



def init(record):
    global _recruit_guard, _transfer_guard, _record, _personal_guard
    import crew_capabilities
    from gui.Scaleform.daapi.business_layer import BusinessHandler, BusinessLobbyHandler
    from gui.Scaleform.daapi.view.lobby.recruitWindow.RecruitWindow import RecruitWindow
    from gui.Scaleform.daapi.view.lobby.hangar.Crew import Crew
    from gui.Scaleform.daapi.view.lobby.barracks.Barracks import Barracks
    from gui import SystemMessages
    capability = crew_capabilities._guard
    if (_recruit_guard is not None or _transfer_guard is not None or recruitment._guard is not None
            or transfer._guard is not None or cross._guard is not None or roster._recruit_guard is not None or capability is None
            or not capability.active or getattr(capability, 'allow_progression', False) is not True):
        raise RuntimeError('explicit exclusive roster capability required')
    classes = dict(Crew=Crew, Barracks=Barracks)
    targets = [(classes[a], b) for a, b, _ in transfer.TARGETS] + [
        (BusinessHandler, '_BusinessHandler__showRecruitWindow'), (RecruitWindow, 'buyTankman')]
    if any((row[0], row[1]) in targets for row in capability.bindings):
        raise RuntimeError('roster callbacks remain blocked by capability guard')
    recruit = _RecruitGuard(BusinessHandler, RecruitWindow, SystemMessages, record, _Native())
    moving = _TransferGuard(classes, SystemMessages, record)
    from gui.Scaleform.daapi.view.lobby.PersonalCase import PersonalCase
    from gui.Scaleform.daapi.view.meta.PersonalCaseMeta import PersonalCaseMeta
    personal = _PersonalGuard(PersonalCase, PersonalCaseMeta, SystemMessages, record, business_class=BusinessLobbyHandler)
    recruit.install()
    try:
        moving.install()
        personal.install()
    except Exception:
        moving.restore()
        recruit.restore()
        raise
    _recruit_guard, _transfer_guard, _record, _personal_guard = recruit, moving, record, personal


def fini():
    global _recruit_guard, _transfer_guard, _scenario, _record, _personal_guard
    if _personal_guard is not None:
        _personal_guard.restore()
        _personal_guard = None
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
        _record('p04i_native_progression_request', **fields)


def native_event(fields):
    if _scenario is not None and _scenario.pending is not None:
        try:
            _scenario.pending['tracker'].observe(fields)
        except (ValueError, KeyError, TypeError) as error:
            _scenario.error = str(error)


def native_window_evidence(window, snapshot):
    from gui.shared import g_itemsCache
    if _personal_guard is None or type(window) is not _personal_guard.window_class:
        raise RuntimeError('original PersonalCase and explicit progression guard required')
    _personal_guard.mask(window)
    row, item = _personal_guard._row(window)
    model = _personal_guard.models[window]
    if not all(key in model for key in ('common', 'skills', 'catalog', 'dossier')):
        return None
    flash = window.flashObject
    if (personal_tab_count(flash) != 4 or int(flash.tabs.selectedIndex) != 2
            or any(flash.tabs.getButtonAt(index).enabled is not False for index in (1, 3))):
        raise RuntimeError('unsupported PersonalCase tabs are not disabled or skills tab is absent')
    for name in ('unloadBtn', 'dismissBtn', 'dropSkillsButton', 'accTeachingOfSkillBtn'):
        if getattr(flash, name).enabled is not False or getattr(flash, name).visible is not False:
            raise RuntimeError('unsupported personal action remains visible/enabled')
    dossier = g_itemsCache.items.getTankmanDossier(row['inventory_id'])
    if dossier is None:
        raise RuntimeError('original tankman dossier required')
    total = dossier.getTotalStats()
    battles, average, next_battles = total.getBattlesCount(), dossier.getAvgXP(), dossier.getNextSkillBattlesLeft()
    packed = dossier.getDossierDescr().makeCompDescr()
    if (battles != 0 or average != 0 or next_battles is not None
            or not isinstance(packed, bytes) or not 6 <= len(packed) <= 4096
            or item.descriptor.dossierCompactDescr != DOSSIER):
        raise RuntimeError('original dossier zero statistics or preserved embedded bytes differs')
    stats = model['dossier'].get('stats')
    achievements = model['dossier'].get('achievements')
    if (type(stats) not in (list, tuple) or len(stats) != 2
            or [group.get('label') for group in stats] != ['common', 'studying']
            or type(achievements) not in (list, tuple) or len(achievements) > 32):
        raise RuntimeError('original dossier output schema differs')
    return dict(inventory_id=row['inventory_id'], role_level=row['role_level'],
                combined_roles=list(item.combinedRoles), catalog=model['catalog'],
                can_learn=model['can_learn'], has_new_skill=bool(item.hasNewSkill),
                skills=list(item.descriptor.skills), last_skill_level=item.descriptor.lastSkillLevel,
                base_sixth=True, base_notice=BASE_NOTICE, combat_signal='NOT_IMPLEMENTED',
                unavailable_tabs=[1, 3], original_common_dossier_skills=True,
                dossier=dict(battles=battles, average_xp=average, next_skill_battles=next_battles,
                             next_skill_xp=dossier.getNextSkillXPLeft(),
                             repacked_hex=binascii.hexlify(packed).decode('ascii'),
                             repacked_bytes=len(packed), repacked_sha256=hashlib.sha256(packed).hexdigest(),
                             persisted_bytes_unchanged=True, statistics=stats,
                             achievement_sections=len(achievements)),
                observation='original Python data providers and PyGFx; pixels are separate evidence')


class _Screenshots(recruitment._Screenshots):
    def capture(self, name, record):
        allowed = ['p04i_initial', 'p04i_relogin_ms1', 'p04i_relogin_is7', 'p04i_low50']
        allowed += ['p04i_' + step[0] for step in STEPS]
        allowed += ['p04i_window_' + str(identity) for identity in (1, 2, 3)]
        allowed += ['p04i_relogin_window_' + str(identity) for identity in (1, 2, 3, 4)]
        if name not in allowed:
            raise ValueError('unsupported progression screenshot basename')
        if name not in self.requested:
            if any(entry.startswith(name + '_') for entry in self._entries()):
                raise ValueError('progression screenshot basename occupied')
            import BigWorld
            self.requested.add(name)
            BigWorld.screenShot('png', name)
            record('p04i_progression_screenshot_requested', basename=name, writer='BigWorld.screenShot')
        names = [entry for entry in self._entries() if re.match(r'\A' + re.escape(name) + r'_[0-9]{3,10}\.png\Z', entry)]
        if not names:
            return None
        if len(names) != 1:
            raise ValueError('ambiguous native progression screenshot')
        from project_preferences import owned
        from ms1_crew_scenario import png_evidence
        path = owned(os.path.join(self.directory, names[0]), self.directory)
        if not os.path.isfile(path) or os.path.islink(path):
            raise ValueError('native progression screenshot must be owned regular file')
        return png_evidence(path, name)


class NativeScenario(transfer.NativeScenario):
    def __init__(self, record, mode, expected, learned=None, settings=None, clock=None):
        global _scenario
        if not callable(record) or mode not in ('learn', 'relogin'):
            raise ValueError('explicit native progression mode required')
        self.expected = checked_expected(expected, ROLE_LEVEL)
        self.learned = checked_learning(learned) if mode == 'learn' else None
        if mode == 'relogin' and learned is not None:
            raise ValueError('read-only relogin cannot carry mutation catalog')
        if (len(self.expected['tankmen']) != 10 or self.expected['free_quota'] != 6
                or self.expected['ms1_crew'] != [4, 5] or self.expected['is7_crew'] != [6, 7, 8, 10, 9]):
            raise ValueError('progression starts with the accepted full H crews and no grant')
        for row, (identity, name, index) in zip(self.expected['tankmen'], LEARNING):
            if row['skills'] != ([] if mode == 'learn' else [name]) or row['vehicle_inventory_id'] != -1:
                raise ValueError('progression initial/final first skills differ')
        self.record, self.mode = record, mode
        self.clock = clock if clock is not None else time.monotonic if hasattr(time, 'monotonic') else time.clock
        self.started = self.clock()
        self.last_time, self.advances, self.phase = self.started, 0, 'wait_hangar'
        self.step, self.pending, self.error = 0, None, None
        self.snapshot, self.ammo, self.ready_since = None, None, None
        self.captures, self.views, self.windows_seen = [], [], []
        self.screenshots = None if settings is None else _Screenshots(settings)
        self.selected, self.selection_ready, self.after_selection = None, None, None
        self.window_identity, self.window_observation = None, None
        if _scenario is not None and _scenario.phase not in ('complete', 'error'):
            raise RuntimeError('only one progression diagnostic permitted')
        _scenario = self

    def emit(self, event, **fields):
        fields.update(version=VERSION, policy=POLICY, step=self.step)
        if 'snapshot' in fields:
            fields.update(native_descriptor_parse_repack=True, native_descriptor_count=len(fields['snapshot']['tankmen']))
        self.record(event, **fields)

    def _select(self, page, vehicle, following):
        self.selected, self.after_selection, self.selection_ready = vehicle, following, None
        self.phase = 'wait_selection'
        page.tankCarousel.vehicleChange(vehicle)
        self.emit('p04i_progression_select', vehicle=vehicle, original_callback='TankCarousel.vehicleChange')

    def _capture(self, name):
        if self.last_time - self.ready_since > 20:
            raise RuntimeError('progression screenshot deadline20s exceeded')
        if self.last_time - self.ready_since < 2:
            return False
        capture = None if self.screenshots is None else self.screenshots.capture(name, self.record)
        if self.screenshots is not None and capture is None:
            return False
        if capture is not None:
            self.captures.append(capture)
            self.emit('p04i_progression_screenshot', screenshot=capture, vehicle=self.selected)
        return True

    def _open(self, page, identity):
        self.window_identity, self.window_observation = identity, None
        self.phase = 'wait_window'
        page.crewPanel.openPersonalCase(identity, 2)
        self.emit('p04i_personal_open', inventory_id=identity, original_callback='Crew.openPersonalCase', arguments=[identity, 2])

    def _advance(self, ready):
        if not ready:
            self.selection_ready = None
            return False
        from gui.WindowsManager import g_windowsManager
        from gui.Scaleform.framework import ViewTypes
        from gui.Scaleform.daapi.settings.views import VIEW_ALIAS
        from gui.Scaleform.framework.managers.containers import POP_UP_CRITERIA
        from gui.Scaleform.Waiting import Waiting
        from CurrentVehicle import g_currentVehicle
        manager = g_windowsManager.window.containerManager
        page = manager.getContainer(ViewTypes.LOBBY_SUB).getView()
        if type(page).__name__ != 'Hangar' or page.flashObject is None or page.crewPanel.flashObject is None:
            raise RuntimeError('original Flash-bound Hangar required')
        if Waiting.isVisible():
            return False
        # Original _PopUpContainer.getView returns None without criteria;
        # unlike the default Hangar container it has no implicit current view.
        window = manager.getContainer(ViewTypes.WINDOW).getView(
            criteria={POP_UP_CRITERIA.VIEW_ALIAS: VIEW_ALIAS.PERSONAL_CASE})
        if self.phase == 'wait_hangar':
            self._select(page, 1, 'initial_capture')
            return False
        if g_currentVehicle.invID != self.selected:
            if self.phase == 'wait_selection':
                self.selection_ready = None
                return False
            raise RuntimeError('native vehicle changed during progression')
        if self.phase == 'wait_selection':
            if self.selection_ready is None:
                self.selection_ready = self.last_time
            if self.last_time - self.selection_ready < 2:
                return False
            actual, ammo = native_snapshot(ROLE_LEVEL), cross.native_ammunition()
            expected = dict(self.expected if self.snapshot is None else self.snapshot, selected_inventory_id=self.selected)
            if actual != expected or self.ammo is not None and ammo != self.ammo:
                raise RuntimeError('native selection changed persistent state')
            self.snapshot, self.ammo = actual, ammo
            self.phase, self.ready_since = self.after_selection, self.last_time
            self.emit('p04i_progression_view', snapshot=actual, ammunition=ammo,
                      efficiency=native_efficiency(actual), readiness=native_readiness(actual))
        if self.phase in ('initial_capture', 'after_capture', 'relogin_capture'):
            if window is not None:
                return False
            if native_snapshot(ROLE_LEVEL) != self.snapshot or cross.native_ammunition() != self.ammo:
                raise RuntimeError('persistent state changed during screenshot')
            name = ('p04i_relogin_' + ('ms1' if self.selected == 1 else 'is7') if self.mode == 'relogin' else
                    'p04i_initial' if self.phase == 'initial_capture' else 'p04i_' + STEPS[self.step][0])
            if not self._capture(name):
                return False
            if self.mode == 'relogin':
                self.views.append(self.selected)
                if len(self.views) == 1:
                    self._select(page, 2, 'relogin_capture')
                else:
                    self._open(page, 1)
                return False
            if self.phase == 'after_capture':
                self.step += 1
                self.pending = None
            if self.step == len(STEPS):
                self._open(page, 4)
                return False
            self.phase = 'action'
        if self.phase == 'action':
            name, command, layout = STEPS[self.step]
            if window is not None or native_snapshot(ROLE_LEVEL) != self.snapshot:
                raise RuntimeError('native callback state/window changed')
            self.emit('p04i_progression_before', name=name, snapshot=self.snapshot, ammunition=self.ammo)
            expected = (projected_transfer(self.snapshot, *layout) if command == 105 else
                        projected_learning(self.snapshot, self.learned[layout[0] - 1]))
            self.pending = dict(tracker=NativeCommandTracker(command, layout), expected=expected)
            if command == 151:
                self._open(page, layout[0])
            else:
                self.phase = 'wait_result'
                callback, args = ('unloadTankman', [self.snapshot[crew_key(layout[0])][layout[1]]]) if layout[2] == -1 else ('equipTankman', [layout[2], layout[1]])
                self.emit('p04i_progression_action', name=name, original_callback='Crew.' + callback,
                          arguments=args, native_cmd=command, layout=layout)
                getattr(page.crewPanel, callback)(*args)
            return False
        if self.phase in ('wait_window', 'window_capture'):
            if window is None or window.flashObject is None:
                return False
            if type(window) is not _personal_guard.window_class or window.tmanInvID != self.window_identity:
                raise RuntimeError('unexpected personal case window')
            if native_snapshot(ROLE_LEVEL) != self.snapshot or cross.native_ammunition() != self.ammo:
                raise RuntimeError('native state changed before skill callback')
            observation = native_window_evidence(window, self.snapshot)
            if observation is None:
                return False
            if self.phase == 'wait_window':
                self.window_observation = observation
                self.emit('p04i_personal_observed', observation=observation, snapshot=self.snapshot)
                self.phase, self.ready_since = 'window_capture', self.last_time
                return False
            basename = ('p04i_relogin_window_' + str(self.window_identity) if self.mode == 'relogin' else
                        'p04i_low50' if self.window_identity == 4 else 'p04i_window_' + str(self.window_identity))
            if not self._capture(basename):
                return False
            if self.mode == 'relogin' or self.window_identity == 4:
                if self.window_identity == 4 and observation['can_learn']:
                    raise RuntimeError('50% recruit must not learn a skill')
                self.windows_seen.append(self.window_identity)
                window.onWindowClose()
                self.phase = 'next_window'
                return False
            identity, skill, index = LEARNING[self.window_identity - 1]
            if skill not in observation['catalog'] or not observation['can_learn']:
                raise RuntimeError('original selectable skill unavailable')
            self.phase = 'wait_result'
            self.emit('p04i_progression_action', name=STEPS[self.step][0], original_callback='PersonalCase.addTankmanSkill',
                      arguments=[identity, skill], native_cmd=151, layout=[identity, index, 0])
            window.addTankmanSkill(identity, skill)
            return False
        if self.phase == 'wait_result':
            tracker = self.pending['tracker']
            if tracker.success is None:
                return False
            actual, ammo = native_snapshot(ROLE_LEVEL), cross.native_ammunition()
            if actual != self.pending['expected'] or ammo != self.ammo:
                raise RuntimeError('native progression differs from exact authoritative expectation')
            self.snapshot = actual
            self.emit('p04i_progression_callback', **tracker.receipt())
            self.emit('p04i_progression_after', name=STEPS[self.step][0], snapshot=actual, ammunition=ammo,
                      efficiency=native_efficiency(actual), readiness=native_readiness(actual))
            if window is not None:
                window.onWindowClose()
            self.phase, self.ready_since = 'after_capture', self.last_time
            return False
        if self.phase == 'next_window':
            if window is not None:
                return False
            if self.mode == 'relogin' and len(self.windows_seen) < 4:
                self._open(page, len(self.windows_seen) + 1)
                return False
            self.emit('p04i_progression_relogin' if self.mode == 'relogin' else 'p04i_progression_final',
                      snapshot=self.snapshot, ammunition=self.ammo, operations=0 if self.mode == 'relogin' else 6,
                      windows_observed=list(self.windows_seen), vehicles_observed=list(self.views),
                      action='read_only' if self.mode == 'relogin' else 'original_callbacks',
                      physical_pointer_input=False, pixels='NOT_RUN')
            self.phase = 'complete'
            return True
        return False
