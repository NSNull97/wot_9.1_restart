# -*- coding: utf-8 -*-
"""Sparse native crew and the original typed dismissal confirmation.

The only Flash compatibility change constructs the original display model
inside its own Flash domain from twelve actual primitive display fields.
No tariff rows, command replies or inventory/cache state are fabricated.
"""
import copy
import hashlib
import math
import os
import re
import time
import traceback
import crew_vehicles
import p04d_crew_ui as recruitment
import p04f_crew_ui as transfer
import p04g_crew_ui as cross
import p04h_crew_ui as roster
import p04i_crew_ui as progression

VERSION = 1
POLICY = 'test_lab.ms1_is7.dismissal.sparse16.no_refund.v1'
ROLE_LEVEL = 50
NOTICE = u'Увольнение необратимо. Платное обучение, сброс навыков и документы пока недоступны.'
MAX_TANKMEN = 16
VEHICLES = progression.VEHICLES
ROW_FIELDS = progression.ROW_FIELDS
SNAPSHOT_FIELDS = progression.SNAPSHOT_FIELDS
DOSSIER_SHA256 = progression.DOSSIER_SHA256
SKILL_IDS = progression.SKILL_IDS
combined_roles = progression.combined_roles
eligible_names = progression.eligible_names
callback_integer = progression.callback_integer
crew_key = progression.crew_key
_assignments = progression._assignments
_recruit_guard = _transfer_guard = _personal_guard = _dismiss_guard = None
_record = _scenario = None
_input_observation_count = 0
INPUT_OBSERVER_PINS = {
    ('scripts/client/gui/Scaleform/daapi/view/meta/InputCheckerMeta.py', 'as_setFormattedControlNumberS'):
        (50, 'a07a7ee689046d4e29fdf9eec47a9e62036dd61fc57ba9dd88615e7fbac06313'),
    ('scripts/client/gui/Scaleform/daapi/view/meta/InputCheckerMeta.py', 'as_setOriginalControlNumberS'):
        (59, 'a07a7ee689046d4e29fdf9eec47a9e62036dd61fc57ba9dd88615e7fbac06313'),
    ('scripts/client/gui/Scaleform/daapi/view/meta/InputCheckerMeta.py', 'as_invalidUserTextS'):
        (68, 'a07a7ee689046d4e29fdf9eec47a9e62036dd61fc57ba9dd88615e7fbac06313'),
    ('scripts/client/gui/Scaleform/daapi/view/lobby/inputChecker/InputChecker.py', 'sendUserInput'):
        (42, 'cb9e860d3ec383bec93b13a02bf48ca85f40a8dd2cab78aa3334802699f94c89')}
TRANSFORMED_FLASH_SHA256 = '592c5c8c6ef71f49b49003c64833d3338dd1323e6fd7f3f477466d2acc5c8fa9'
DISMISSAL_RESOURCE = 'gui/flash/Application.swf'
UNCHANGED_CHILD_SHA256 = '33a92ccdcf2ef278e41e5ca1dd349e2eff3f323486e9a1c3065d0809336fffe5'


def native_flash_resource(record):
    """Read the actual engine resource resolution; installer presence is separate."""
    import ResMgr
    section = ResMgr.openSection(DISMISSAL_RESOURCE)
    if section is None:
        raise RuntimeError('native dismissal movie resource is absent')
    raw = section.asBinary
    if not isinstance(raw, bytes) or not 8 <= len(raw) <= 16 * 1024 * 1024:
        raise RuntimeError('bounded native dismissal movie resource required')
    digest = hashlib.sha256(raw).hexdigest()
    record('p04j_native_flash_resource', resource=DISMISSAL_RESOURCE,
           bytes=len(raw), sha256=digest, expected_sha256=TRANSFORMED_FLASH_SHA256,
           matches_transformed=digest == TRANSFORMED_FLASH_SHA256, read_only=True,
           compatibility='parent_model_construction', acceptance='PENDING_NATIVE_READBACK')
    if digest != TRANSFORMED_FLASH_SHA256:
        raise RuntimeError('engine resolved a different dismissal movie resource')
    child = ResMgr.openSection('gui/flash/dismissTankmanDialog.swf')
    child_raw = None if child is None else child.asBinary
    if not isinstance(child_raw, bytes) or not 8 <= len(child_raw) <= 16 * 1024 * 1024:
        raise RuntimeError('bounded unchanged child resource required')
    child_digest = hashlib.sha256(child_raw).hexdigest()
    record('p04j_native_flash_dependency', resource='gui/flash/dismissTankmanDialog.swf',
           bytes=len(child_raw), sha256=child_digest, expected_sha256=UNCHANGED_CHILD_SHA256,
           unchanged_original=child_digest == UNCHANGED_CHILD_SHA256, read_only=True)
    if child_digest != UNCHANGED_CHILD_SHA256:
        raise RuntimeError('dismissal compatibility requires the unchanged original child movie')

def integer(value, low, high):
    return recruitment._integer(value, low, high)


def vehicles(snapshot=None):
    """Served vehicles: MS-1/IS-7 pins, or (CREW-ANY) the owned catalog vehicles."""
    return crew_vehicles.vehicles(VEHICLES, snapshot)


def max_tankmen():
    return crew_vehicles.max_tankmen(MAX_TANKMEN)


def checked_expected(value, role_level=None):
    """Validate roster structure; a supplied level also binds new H members.

    Old identities keep their accepted, pinned descriptors. New descriptor
    hashes remain part of the caller's exact expected snapshot/catalog rather
    than an invented local descriptor generator.
    """
    if type(value) is not dict or set(value) != crew_vehicles.snapshot_fields(SNAPSHOT_FIELDS):
        raise ValueError('exact native roster snapshot required')
    if role_level is not None:
        integer(role_level, 0, 100)
    integer(value['database_id'], 1, 2147483647)
    capacity, served = max_tankmen(), vehicles(value)
    if crew_vehicles.enabled():
        # Any garage vehicle may be selected; only served ones accept crew actions.
        integer(value['selected_inventory_id'], -1, 2147483647)
    else:
        integer(value['selected_inventory_id'], 1, 2)
    integer(value['free_quota'], 0, capacity)
    for field in ('credits', 'gold'):
        integer(value[field], 0, 9223372036854775807)
    members = value['tankmen']
    if type(members) is not list or not 0 <= len(members) <= capacity:
        raise ValueError('bounded native roster membership required')
    seats = {}
    for vehicle, crew in crew_vehicles.crew_items(value):
        if type(crew) is not list or len(crew) != len(served[vehicle][3]):
            raise ValueError('source-bound native crew shape required')
        for slot, identity in enumerate(crew):
            if identity is None:
                continue
            integer(identity, 1, capacity)
            if identity in seats:
                raise ValueError('tankman occupies more than one native seat')
            seats[identity] = (vehicle, slot)
    identities = []
    for row in members:
        if type(row) is not dict or set(row) != ROW_FIELDS:
            raise ValueError('exact native roster row required')
        identity = integer(row['inventory_id'], 1, capacity)
        if identities and identity <= identities[-1]:
            raise ValueError('sorted unique sparse native identities required')
        identities.append(identity)
        integer(row['nation_id'], 0, 0)
        # T-34 is source type 0 (catalog compact ID 1); the legacy pins start at 1.
        integer(row['vehicle_type_id'], 0 if crew_vehicles.enabled() else 1, 255)
        if row['vehicle_type_id'] not in crew_vehicles.trained_types((13, 28)):
            raise ValueError('unsupported trained vehicle type')
        integer(row['role_level'], 0, 100)
        if row['role'] not in crew_vehicles.primary_roles(('commander', 'driver', 'gunner', 'loader')):
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
        if crew_vehicles.enabled():
            if row['vehicle_inventory_id'] != -1:
                crew_vehicles.vehicle_id(row['vehicle_inventory_id'], value)
            integer(row['slot'], -1, 7)
        else:
            integer(row['vehicle_inventory_id'], -1, 2)
            integer(row['slot'], -1, 4)
        actual = (row['vehicle_inventory_id'], row['slot'])
        if actual != seats.get(identity, (-1, -1)):
            raise ValueError('native tankman and vehicle assignments disagree')
        if actual[0] != -1 and row['role'] != served[actual[0]][3][actual[1]]:
            raise ValueError('native primary role does not match seat')
        if identity <= 3:
            role = 'commander' if identity == 1 else 'driver'
            pin = transfer.COMMANDER_SHA256 if identity == 1 else recruitment.DRIVER_SHA256
            if (row['vehicle_type_id'] != 13 or row['role'] != role
                    or row['role_level'] != 100 or not row['skills'] and row['sha256'] != pin):
                raise ValueError('accepted original tankman descriptor changed')
        elif role_level is not None and row['role_level'] != role_level:
            raise ValueError('new tankman level differs from selected policy')
    if set(seats) - set(identities):
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
    if not isinstance(tankmen, ItemsCollection) or not 0 <= len(tankmen) <= max_tankmen():
        raise ValueError('bounded original ItemsCollection required')
    rows = []
    for identity, item in sorted(tankmen.items()):
        integer(identity, 1, max_tankmen())
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
    if crew_vehicles.enabled():
        # Owned catalog vehicles, each checked against the client's own type.
        table = crew_vehicles.live_vehicles()
        value['vehicles'] = dict((identity, [entry[0], entry[1], entry[2], list(entry[3])]) for identity, entry in table.items())
        value['crews'] = crew_vehicles.live_crews(table)
        return checked_expected(value, role_level)
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
    for identity, crew in crew_vehicles.crew_items(snapshot):
        vehicle = g_itemsCache.items.getVehicle(identity)
        raw = vehicle.isCrewFull
        full = all(member is not None for member in crew)
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


def member_map(snapshot):
    return dict((row['inventory_id'], row) for row in snapshot['tankmen'])


def member_row(snapshot, identity):
    row = member_map(snapshot).get(callback_integer(identity, 1, max_tankmen()))
    if row is None:
        raise ValueError('active owned native tankman required')
    return row


def projected_transfer(snapshot, vehicle, slot, identity):
    """Expected evidence only; never writes a GUI object or native cache."""
    value = checked_expected(snapshot, ROLE_LEVEL)
    if crew_vehicles.enabled():
        vehicle = crew_vehicles.vehicle_id(vehicle, value)
    else:
        vehicle = integer(vehicle, 1, 2)
    roles = vehicles(value)[vehicle][3]
    slot = integer(slot, -1, len(roles) - 1)
    identity = integer(identity, -1, max_tankmen())
    crew = crew_vehicles.crew_of(value, vehicle)
    if identity == 0 or slot == -1 and identity != -1:
        raise ValueError('unsupported native transfer selection')
    if identity > 0:
        row = member_row(value, identity)
        if row['vehicle_inventory_id'] != -1:
            raise ValueError('original selectable candidate must be in barracks')
        if row['role'] != roles[slot]:
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


class _TransferGuard(transfer._TransferGuard):
    def __init__(self, classes, messages, record, snapshot=None):
        transfer._TransferGuard.__init__(self, classes, messages, record,
                                        native_snapshot if snapshot is None else snapshot)

    def emit(self, event, **fields):
        if self.events >= 2048 and not event.endswith('_policy'):
            raise RuntimeError('roster transfer event budget exhausted')
        self.events += 1
        fields.update(version=VERSION, policy=POLICY)
        self.record(event.replace('p04f_transfer', 'p04j_transfer'), **fields)

    def _deny(self, callback):
        self.emit('p04j_transfer_denied', callback=callback, original_callback_called=False)
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
                    identity = callback_integer(supplied[0], 1, max_tankmen())
                    if crew_vehicles.enabled():
                        crew_vehicles.vehicle_id(vehicle, state)
                    slot = callback_integer(supplied[1], 0, len(vehicles(state)[vehicle][3]) - 1)
                    projected_transfer(state, vehicle, slot, identity)
                elif name == 'unloadTankman':
                    if len(supplied) != 1:
                        raise ValueError('unload callback arity')
                    member = member_row(state, supplied[0])
                    if callback == 'Barracks.unloadTankman':
                        vehicle = member['vehicle_inventory_id']
                    if vehicle not in vehicles(state) or member['vehicle_inventory_id'] != vehicle:
                        raise ValueError('tankman is not seated in the original target')
                    slot, identity = member['slot'], -1
                else:
                    if crew_vehicles.enabled():
                        crew_vehicles.vehicle_id(vehicle, state)
                    if supplied or all(item is None for item in crew_vehicles.crew_of(state, vehicle)):
                        raise ValueError('whole crew unload requires occupied seats')
                    slot, identity = -1, -1
            except ValueError:
                return guard._deny(callback)
            guard.emit('p04j_transfer_ui_call', callback=callback, vehicle=vehicle, slot=slot,
                       tankman_id=identity, native_cmd=105, original_callback_called=True)
            return original(*args, **kwargs)
        return wrapped


class _Native(object):
    def state(self):
        return native_snapshot(ROLE_LEVEL)


class _RecruitGuard(roster._RosterRecruitGuard):
    def _state(self):
        if not self.active:
            raise RuntimeError('dismissal roster callback after cleanup')
        return checked_expected(self.native.state(), ROLE_LEVEL)


class _PersonalGuard(progression._PersonalGuard):
    def _row(self, window):
        if not self.active:
            raise RuntimeError('personal case callback after cleanup')
        state = checked_expected(self.snapshot(), ROLE_LEVEL)
        row = member_row(state, window.tmanInvID)
        item = self.member(row['inventory_id'])
        if item is None or item.invID != row['inventory_id'] or tuple(item.combinedRoles) != combined_roles(row):
            raise ValueError('original personal case member or combined roles differs')
        if window not in self.windows:
            if len(self.windows) >= 32:
                raise RuntimeError('personal case instance budget exceeded')
            self.windows.append(window)
        self.models.setdefault(window, {})
        return row, item

    def _open(self, original):
        guard = self
        def opened(owner, event):
            if not guard.active:
                raise RuntimeError('personal case entry after cleanup')
            state, ctx = checked_expected(guard.snapshot(), ROLE_LEVEL), event.ctx
            if (type(ctx) is not dict or set(ctx) - set(('tankmanID', 'page'))
                    or type(ctx.get('tankmanID')) not in recruitment.integer_types
                    or ctx['tankmanID'] not in member_map(state)
                    or type(ctx.get('page', -1)) not in recruitment.integer_types
                    or ctx.get('page', -1) not in (-1, 0, 2)):
                guard.record('p04j_personal_denied', action='open_unsupported_page', original_called=False)
                guard.messages.pushMessage(NOTICE, type=guard.messages.SM_TYPE.Warning)
                return
            return original(owner, event)
        return opened

    def mask(self, window):
        progression._PersonalGuard.mask(self, window)
        window.flashObject.dismissBtn.visible = True
        window.flashObject.dismissBtn.enabled = True


DISPLAY_CLASS = 'net.wg.gui.lobby.tankman.SkillDropModel'
DISPLAY_FIELDS = set(('nationID', 'tankmanName', 'tankmanIcon', 'roleIcon', 'roleLevel',
    'skillsCount', 'lastSkill', 'lastSkillLevel', 'preLastSkill', 'hasNewSkill',
    'newSkillsCount', 'lastNewSkillLevel'))


def display_fields(value, row, packed, new_skills):
    """Read only actual original packTankman fields used by the dismissal view."""
    if (type(value) is not dict or set(value) != set(('money', 'tankman', 'dropSkillsCost',
            'hasNewSkills', 'newSkills', 'defaultSavingMode')) or value['tankman'] != packed
            or value['newSkills'] != new_skills or value['defaultSavingMode'] != 0):
        raise ValueError('original dismissal VO or actual member packing differs')
    skills = packed['skills']
    if (type(skills) not in (list, tuple) or len(skills) != len(row['skills'])
            or packed['nationID'] != row['nation_id'] or packed['roleLevel'] != row['role_level']
            or type(value['hasNewSkills']) is not bool
            or type(new_skills) not in (list, tuple) or len(new_skills) != 2):
        raise ValueError('original dismissal qualification or skills differ')
    result = dict(nationID=packed['nationID'],
        tankmanName=packed['firstUserName'] + u' ' + packed['lastUserName'],
        tankmanIcon=packed['icon']['big'], roleIcon=packed['iconRole']['small'],
        roleLevel=packed['roleLevel'], skillsCount=len(skills),
        lastSkill=None if not skills else skills[-1]['icon']['small'],
        lastSkillLevel=0 if not skills else skills[-1]['level'],
        preLastSkill=None if len(skills) < 2 else skills[-2]['icon']['small'],
        hasNewSkill=value['hasNewSkills'], newSkillsCount=new_skills[0], lastNewSkillLevel=new_skills[1])
    for key in ('tankmanName', 'tankmanIcon', 'roleIcon', 'lastSkill', 'preLastSkill'):
        field = result[key]
        if field is None and key in ('lastSkill', 'preLastSkill'):
            continue
        if not isinstance(field, recruitment.string_types) or not 0 < len(field) <= 2048:
            raise ValueError('bounded original display string required')
    for key, low, high in (('nationID', 0, 0), ('roleLevel', 0, 100), ('skillsCount', 0, 1),
            ('lastSkillLevel', 0, 0), ('newSkillsCount', 0, 1), ('lastNewSkillLevel', 0, 100)):
        callback_integer(result[key], low, high)
    if set(result) != DISPLAY_FIELDS:
        raise RuntimeError('dismissal display field contract changed')
    return result


class _DismissGuard(object):
    def __init__(self, classes, dialog, meta, record, snapshot=None, pack=None):
        self.classes, self.dialog, self.meta, self.record = classes, dialog, meta, record
        self.snapshot = native_snapshot if snapshot is None else snapshot
        self.pack = self._pack if pack is None else pack
        self.bindings, self.windows = [], {}
        self.active, self.current = False, None
        self.open_count = 0

    @staticmethod
    def _pack(item):
        from gui.shared.gui_items.serializers import packTankman
        return packTankman(item)

    def _entry(self, original, callback):
        guard = self
        def entered(owner, identity):
            if not guard.active or guard.current is not None or guard.open_count >= 32:
                raise RuntimeError('dismissal dialog lifecycle or budget differs')
            row = member_row(checked_expected(guard.snapshot(), ROLE_LEVEL), identity)
            guard.open_count += 1
            guard.record('p04j_dismissal_open', inventory_id=row['inventory_id'],
                original_callback=callback, original_called=True)
            return original(owner, identity)
        return entered

    def _model(self, original):
        guard = self
        def model(window, value):
            if not guard.active or type(window) is not guard.dialog:
                raise RuntimeError('original dismissal window required')
            item = window._DismissTankmanDialog__tankman
            row = member_row(checked_expected(guard.snapshot(), ROLE_LEVEL), item.invID)
            if hashlib.sha256(item.strCD).hexdigest() != row['sha256']:
                raise ValueError('dismissal member changed before display')
            fields = display_fields(value, row, guard.pack(item), item.newSkillCount)
            inited = window._isDAAPIInited()
            guard.current = window
            guard.windows[window] = dict(inventory_id=row['inventory_id'], fields=fields,
                protected=not (row['role_level'] < 100 and fields['lastSkill'] is None and not fields['hasNewSkill']),
                pending_reads=0, bridge_observed=False)
            original(window, fields)
            guard.record('p04j_dismissal_model_sent', inventory_id=row['inventory_id'], display_fields=fields,
                native_class=DISPLAY_CLASS, native_constructor_in_flash=True, supplied_tariff_rows=False,
                descriptor_sha256=row['sha256'], daapi_inited_before=bool(inited),
                source_argument='actual_primitive_display_fields', typed_object_bridge=False,
                immediate_model_null=window.flashObject.model is None,
                original_meta_called=True, bridge_acceptance='PENDING_NATIVE_READBACK')
        return model

    def _dispose(self, original):
        guard = self
        def disposed(window):
            result = original(window)
            guard.windows.pop(window, None)
            if guard.current is window:
                guard.current = None
            guard.record('p04j_dismissal_disposed', original_called=True)
            return result
        return disposed

    def _populate(self, original):
        guard = self
        def populated(window):
            guard.record('p04j_dismissal_populate', phase='call', original_called=True)
            try:
                result = original(window)
            except Exception as error:
                # Preserve the original asynchronous exception independently
                # in the bounded trace, then re-raise the same exception.
                import sys
                stack = traceback.extract_tb(sys.exc_info()[2])[-16:]
                guard.record('p04j_dismissal_exception', phase='original_populate',
                    exception_type=type(error).__name__, message=str(error)[:2048],
                    stack=[dict(source=row[0], line=row[1], method=row[2]) for row in stack],
                    rethrown=True, original_called=True)
                if _scenario is not None:
                    _scenario.error = 'original dismissal populate raised ' + type(error).__name__
                    _scenario.failure_window = window
                raise
            guard.record('p04j_dismissal_populate', phase='return', original_called=True)
            return result
        return populated

    def install(self):
        if self.active:
            raise RuntimeError('dismissal guard already installed')
        for name, cls in self.classes.items():
            original = cls.__dict__['dismissTankman']
            self.bindings.append((cls, 'dismissTankman', original, self._entry(original, name + '.dismissTankman')))
        original = self.meta.__dict__['as_tankManS']
        self.bindings.append((self.meta, 'as_tankManS', original, self._model(original)))
        original = self.dialog.__dict__['_dispose']
        self.bindings.append((self.dialog, '_dispose', original, self._dispose(original)))
        original = self.dialog.__dict__['_populate']
        self.bindings.append((self.dialog, '_populate', original, self._populate(original)))
        for cls, name, original, replacement in self.bindings:
            if cls.__dict__.get(name) is not original:
                raise RuntimeError('dismissal callback changed before installation')
        for cls, name, original, replacement in self.bindings:
            setattr(cls, name, replacement)
        self.active = True
        self.record('p04j_dismissal_policy', phase='install', original_cmd=306, supplied_tariff_rows=False)

    def restore(self):
        if not self.active:
            return
        for cls, name, original, replacement in self.bindings:
            if cls.__dict__.get(name) is not replacement:
                raise RuntimeError('dismissal callback changed during cleanup')
        for cls, name, original, replacement in self.bindings:
            setattr(cls, name, original)
        self.active = False
        self.current = None
        self.record('p04j_dismissal_policy', phase='restore', original_binding_restored=True)


def init(record):
    global _recruit_guard, _transfer_guard, _personal_guard, _dismiss_guard, _record, _input_observation_count
    import crew_capabilities
    from gui.Scaleform.daapi.business_layer import BusinessHandler, BusinessLobbyHandler
    from gui.Scaleform.daapi.view.lobby.recruitWindow.RecruitWindow import RecruitWindow
    from gui.Scaleform.daapi.view.lobby.hangar.Crew import Crew
    from gui.Scaleform.daapi.view.lobby.barracks.Barracks import Barracks
    from gui.Scaleform.daapi.view.lobby.PersonalCase import PersonalCase
    from gui.Scaleform.daapi.view.meta.PersonalCaseMeta import PersonalCaseMeta
    from gui.Scaleform.daapi.view.dialogs.DismissTankmanDialog import DismissTankmanDialog
    from gui.Scaleform.daapi.view.meta.DismissTankmanDialogMeta import DismissTankmanDialogMeta
    from gui import SystemMessages
    capability = crew_capabilities._guard
    if (any(value is not None for value in (_recruit_guard, _transfer_guard, _personal_guard, _dismiss_guard,
            progression._personal_guard, roster._recruit_guard, cross._guard, transfer._guard, recruitment._guard))
            or capability is None or not capability.active or getattr(capability, 'allow_dismissal', False) is not True):
        raise RuntimeError('exclusive explicit dismissal capability required')
    native_flash_resource(record)
    def record_inherited(event, **fields):
        record(event.replace('p04i_', 'p04j_'), **fields)
    guards = [
        _RecruitGuard(BusinessHandler, RecruitWindow, SystemMessages, record, _Native()),
        _TransferGuard(dict(Crew=Crew, Barracks=Barracks), SystemMessages, record),
        _PersonalGuard(PersonalCase, PersonalCaseMeta, SystemMessages, record_inherited,
                       snapshot=native_snapshot, business_class=BusinessLobbyHandler),
        _DismissGuard(dict(PersonalCase=PersonalCase, Barracks=Barracks), DismissTankmanDialog,
                      DismissTankmanDialogMeta, record)]
    installed = []
    try:
        for guard in guards:
            guard.install()
            installed.append(guard)
    except Exception:
        for guard in reversed(installed):
            guard.restore()
        raise
    _recruit_guard, _transfer_guard, _personal_guard, _dismiss_guard = guards
    _record = record
    _input_observation_count = 0


def fini():
    global _recruit_guard, _transfer_guard, _personal_guard, _dismiss_guard, _record, _scenario, _input_observation_count
    for guard in (_dismiss_guard, _personal_guard, _transfer_guard, _recruit_guard):
        if guard is not None:
            guard.restore()
    _recruit_guard = _transfer_guard = _personal_guard = _dismiss_guard = None
    _record = _scenario = None
    _input_observation_count = 0


def observe_input_profile(frame, phase):
    """Passively bind original initialization and Flash-computed validation.

    No wrapper supplies setter values or callback booleans. Profile hooks see
    the unchanged original calls, including initialization before registration.
    """
    global _input_observation_count
    code, values = frame.f_code, frame.f_locals
    pin = INPUT_OBSERVER_PINS.get((code.co_filename, code.co_name))
    if pin is None or phase not in ('call', 'return') or _dismiss_guard is None:
        return
    if (code.co_firstlineno, hashlib.sha256(code.co_code).hexdigest()) != pin:
        raise RuntimeError('original input observer source differs')
    if _input_observation_count >= 128:
        raise RuntimeError('native input observation budget exhausted')
    _input_observation_count += 1
    owner, value = values.get('self'), values.get('value')
    validation_setter = code.co_name == 'as_invalidUserTextS'
    if validation_setter and type(value) is not bool:
        raise RuntimeError('original validation setter Boolean required')
    if not validation_setter and (not isinstance(value, recruitment.string_types) or len(value) > 64):
        raise RuntimeError('bounded original input value required')
    window = _dismiss_guard.current
    linked = (window is not None and
              getattr(window, '_DismissTankmanDialog__inputChecker', None) is owner)
    info = _dismiss_guard.windows.get(window) if linked else None
    fields = dict(source=code.co_filename, source_line=code.co_firstlineno,
        method=code.co_name, phase=phase, checker_owner_id=id(owner), value=value,
        value_type=type(value).__name__, daapi_inited=bool(owner._isDAAPIInited()),
        dialog_owner_id=id(window) if linked else None,
        inventory_id=info['inventory_id'] if info is not None else None,
        original_called=True, passive=True)
    if code.co_name == 'sendUserInput':
        valid = values.get('isValidSyntax')
        if type(valid) is not bool:
            raise RuntimeError('original native input callback Boolean required')
        fields['native_callback_valid'] = valid
        _record('p04j_native_input_callback', **fields)
        if info is not None:
            callbacks = info.setdefault('input_callbacks' if phase == 'call' else 'input_callback_returns', [])
            callbacks.append(dict(value=value, native_callback_valid=valid,
                                  checker_owner_id=id(owner)))
    else:
        if fields['daapi_inited']:
            formatted = owner.flashObject.formattedControlText
            if not isinstance(formatted, recruitment.string_types) or len(formatted) > 64:
                raise RuntimeError('bounded native formatted control readback required')
            fields['formatted_control_text'] = formatted
        if validation_setter:
            fields['native_validation_accepted'] = owner.flashObject.isInvalidUserText if fields['daapi_inited'] else None
            if info is not None:
                info.setdefault('input_validation_setters', []).append(dict(phase=phase, value=value,
                    checker_owner_id=id(owner), daapi_inited=fields['daapi_inited']))
        _record('p04j_native_input_validation_setter' if validation_setter else 'p04j_native_input_initialization', **fields)


def observe_profile(frame, phase):
    if _record is None:
        return
    observe_input_profile(frame, phase)
    code, values = frame.f_code, frame.f_locals
    if (phase == 'call' and code.co_name == 'onButtonClick' and code.co_filename == BUTTON_PIN[0]
            and _dismiss_guard is not None and type(values.get('self')) is _dismiss_guard.dialog):
        window = values['self']
        if ((code.co_filename, code.co_firstlineno, hashlib.sha256(code.co_code).hexdigest()) != BUTTON_PIN
                or window not in _dismiss_guard.windows):
            raise RuntimeError('original confirmation callback source or window differs')
        _record('p04j_native_confirmation_button', source=code.co_filename,
                source_line=code.co_firstlineno, source_code_sha256=BUTTON_PIN[2],
                method=code.co_name, phase=phase, owner_id=id(window), dialog_owner_id=id(window),
                inventory_id=_dismiss_guard.windows[window]['inventory_id'], button_id=values.get('buttonID'))
        return
    if (phase != 'return' or code.co_filename != 'scripts/client/Account.py'
            or code.co_name != '__doCmd' or values.get('cmd') not in (105, 151, 306, 309)):
        return
    if (code.co_firstlineno, hashlib.sha256(code.co_code).hexdigest()) != progression.COMMAND_PIN:
        raise RuntimeError('original dismissal command observer source differs')
    command, args = values['cmd'], values.get('args')
    if type(args) is not tuple or len(args) != (4 if command == 309 else 3):
        raise ValueError('original dismissal command argument shape differs')
    if any(type(value) not in recruitment.integer_types for value in args):
        raise ValueError('native integer arguments required')
    fields = dict(source=code.co_filename, source_line=code.co_firstlineno, method=code.co_name,
        phase=phase, owner_id=id(values.get('self')), native_cmd=command,
        request_id=integer(values.get('requestID'), 1, 32767), layout=list(args))
    _record('p04j_native_dismissal_request', **fields)
    if _scenario is not None and _scenario.mode == 'preflight':
        _scenario.error = 'native mutation observed during confirmation-only preflight'


def native_event(fields):
    if _scenario is None:
        return
    event = fields.get('event')
    try:
        if event == 'p04j_native_confirmation_button':
            active = getattr(_scenario, 'engine_input', None)
            if (active is None or active['stage'] not in ('correct', 'simple')
                    or active['inventory_id'] != fields.get('inventory_id')
                    or active['dialog_owner_id'] != fields.get('dialog_owner_id')
                    or fields.get('button_id') != 'submit' or _scenario.button_events):
                raise ValueError('unexpected original confirmation callback or blocked input submitted')
            _scenario.button_events.append(dict(fields))
        if event == 'p04j_native_dismissal_request':
            if (_scenario.mode != 'dismiss' or getattr(_scenario, 'preflight_active', False)
                    or _scenario.pending is None):
                raise ValueError('native mutation observed outside explicit dismissal operation')
            if fields.get('native_cmd') == 306 and len(_scenario.button_events) != 1:
                raise ValueError('native dismissal did not follow actual original button callback')
        if _scenario.pending is not None:
            _scenario.pending['tracker'].observe(fields)
    except (ValueError, KeyError, TypeError) as error:
        _scenario.error = str(error)


def diagnostic_flash_surface(window):
    """Bounded read-only evidence independent of the typed model getter."""
    paths = ('visible', 'model', 'secondBtn.visible', 'secondBtn.enabled',
             'secondBtn.focused', 'secondBtn.label', 'secondBtn.data.id',
             'inputChecker.visible', 'inputChecker.textInput.text',
             'inputChecker.textInput.focused', 'inputChecker.formattedControlText',
             'inputChecker.isValidControlInput', 'inputChecker.isInvalidUserText',
             'mainBlock.nameField.text', 'mainBlock.roleLevelField.text',
             'mainBlock.tankmanPic.source', 'mainBlock.roleIcon.source', 'questionTf.text',
             'inputChecker.body.text', 'inputChecker.body.htmlText',
             'inputChecker.body.width', 'inputChecker.body.height',
             'inputChecker.body.textWidth', 'inputChecker.body.textHeight',
             'inputChecker.body.numLines', 'inputChecker.body.wordWrap',
             'inputChecker.body.multiline', 'inputChecker.body.autoSize')
    result = {}
    for path in paths:
        try:
            value = window.flashObject
            for name in path.split('.'):
                value = getattr(value, name)
            if value is None or type(value) in (bool,) + recruitment.integer_types:
                result[path] = value
            elif isinstance(value, recruitment.string_types):
                result[path] = value[:2048]
            elif type(value) is float and not math.isnan(value) and not math.isinf(value):
                result[path] = value
            else:
                result[path] = dict(python_type=type(value).__name__)
        except Exception as error:
            # Diagnostic uncertainty is recorded explicitly, never converted
            # into successful field readback or used to change UI state.
            result[path] = dict(read_error=type(error).__name__, message=str(error)[:256])
    return result


def _native_integral(value, low, high):
    if (type(value) not in recruitment.integer_types + (float,)
            or math.isnan(value) or math.isinf(value) or value != int(value)
            or not low <= value <= high):
        raise RuntimeError('finite integral native display scalar required')
    return int(value)


def rendered_dismissal_fields(flash, expected, protected):
    """Read the original draw/setData widgets; never write or invent a model.

    Native11 rendered the correct portrait, name, qualification and skill while
    PyGFx returned None for the typed model slot. Primitive widgets are the
    independently source-bound output of the unchanged native renderer.
    """
    block = flash.mainBlock
    result = dict(tankman_name=block.nameField.text, portrait=block.tankmanPic.source,
        role_icon=block.roleIcon.source, role_level_text=block.roleLevelField.text)
    if (result['tankman_name'] == '' and result['portrait'] is None
            and result['role_icon'] is None and result['role_level_text'] == ''):
        return None
    wanted = dict(tankman_name=expected['tankmanName'], portrait=expected['tankmanIcon'],
        role_icon=expected['roleIcon'], role_level_text=str(expected['roleLevel']) + '%')
    if result != wanted:
        raise RuntimeError('original rendered dismissal identity or qualification differs')
    result['role_level_bar'] = _native_integral(block.specLevelBar.frontPosition, 0, 100)
    if result['role_level_bar'] != expected['roleLevel']:
        raise RuntimeError('original dismissal qualification bar differs')
    result['nation'] = block.nation
    if expected['nationID'] != 0 or result['nation'] != 'ussr':
        raise RuntimeError('original rendered dismissal nation differs')
    result['skills'] = dict(main=block.mainSkillItem.visible,
        additional=block.additionalSkillItem.visible,
        free1=block.freeSkillItem1.visible, free2=block.freeSkillItem2.visible)
    if any(type(value) is not bool for value in result['skills'].values()):
        raise RuntimeError('original skill visibility Boolean required')
    # J's bounded native proof covers a single learned0 skill and simple50.
    # Other native UI paths remain original; this observer does not guess them.
    if expected['hasNewSkill'] or expected['newSkillsCount'] or expected['lastNewSkillLevel']:
        raise RuntimeError('dismissal diagnostic has an unsupported new-skill display')
    learned = expected['skillsCount'] == 1
    if (not learned and (protected or expected['roleLevel'] >= 100)
            or learned and not protected):
        raise RuntimeError('unsupported source-bound dismissal rendering branch')
    if result['skills'] != dict(main=learned, additional=False, free1=False, free2=False):
        raise RuntimeError('original rendered skill visibility differs')
    result['main_skill'] = None
    if learned:
        item = block.mainSkillItem
        result['main_skill'] = dict(icon=item.iconSource, type=item.type,
            level=_native_integral(item.level, 0, 100), count=_native_integral(item.count, 0, 16))
        # count remains the original widget default0 for TYPE_CURRENT_SKILL;
        # it is not the member's skillsCount1.
        if result['main_skill'] != dict(icon=expected['lastSkill'], type='current_skill',
                level=expected['lastSkillLevel'], count=0):
            raise RuntimeError('original rendered learned skill differs')
    return result


def confirmation_observation(window):
    if _dismiss_guard is None or window not in _dismiss_guard.windows or type(window) is not _dismiss_guard.dialog:
        raise RuntimeError('registered original dismissal confirmation required')
    from gui.Scaleform.daapi.view.dialogs import DIALOG_BUTTON_ID
    info, flash = _dismiss_guard.windows[window], window.flashObject
    if flash is None or window._DismissTankmanDialog__inputChecker is None:
        return None
    flash.validateNow()
    model = flash.model
    rendered = rendered_dismissal_fields(flash, info['fields'], info['protected'])
    if rendered is None:
        info['pending_reads'] += 1
        _dismiss_guard.record('p04j_dismissal_model_pending', inventory_id=info['inventory_id'],
            observation=info['pending_reads'], daapi_inited=bool(window._isDAAPIInited()),
            native_constructor_in_flash=True, reason='original_renderer_blank')
        if info['pending_reads'] >= 3:
            raise RuntimeError('original dismissal renderer remains blank after three native observations')
        return None
    if model is not None and any(getattr(model, key) != value for key, value in info['fields'].items()):
        raise RuntimeError('original typed dismissal model changed')
    actual_model_readback = model is not None
    typed_model_readback = 'AVAILABLE_VERIFIED' if actual_model_readback else 'UNAVAILABLE_OBSERVED'
    if not info['bridge_observed']:
        _dismiss_guard.record('p04j_dismissal_model', inventory_id=info['inventory_id'], display_fields=info['fields'],
            native_class=DISPLAY_CLASS, native_constructor_in_flash=True, supplied_tariff_rows=False,
            original_confirmation_preserved=True, actual_model_readback=actual_model_readback,
            typed_model_readback=typed_model_readback, source_bound_native_rendering=True,
            rendered_fields=rendered,
            pending_observations=info['pending_reads'])
        info['bridge_observed'] = True
    if flash.secondBtn.data.id != DIALOG_BUTTON_ID.SUBMIT:
        raise RuntimeError('source-bound confirmation button identity differs')
    checker = flash.inputChecker
    result = dict(inventory_id=info['inventory_id'], protected=info['protected'],
        display_fields=dict(info['fields']), input_visible=checker.visible,
        submit_id=flash.secondBtn.data.id,
        input_text=checker.textInput.text,
        original_control=window._DismissTankmanDialog__inputChecker._InputChecker__originalControlNumber,
        python_formatted_control=window._DismissTankmanDialog__inputChecker._InputChecker__formattedControlNumber,
        formatted_control_text=checker.formattedControlText,
        checker_owner_id=id(window._DismissTankmanDialog__inputChecker),
        input_focus=_native_integral(checker.textInput.focused, 0, 2147483647),
        raw_boolean_observations=dict(submit_enabled=flash.secondBtn.enabled,
            native_control_match=checker.isValidControlInput,
            native_validation_accepted=checker.isInvalidUserText),
        boolean_readback='UNAVAILABLE_OBSERVED',
        native_validation_semantics='control_value_match',
        source_bound_validation=info.get('last_input_evidence'),
        actual_model_readback=actual_model_readback, typed_model_readback=typed_model_readback,
        source_bound_native_rendering=True, rendered_fields=rendered, supplied_tariff_rows=False)
    for value in [result['input_visible']] + list(result['raw_boolean_observations'].values()):
        if type(value) is not bool:
            raise RuntimeError('original Flash Boolean readback required')
    for field in ('input_text', 'original_control', 'python_formatted_control', 'formatted_control_text'):
        if not isinstance(result[field], recruitment.string_types) or len(result[field]) > 64:
            raise RuntimeError('bounded native confirmation string required')
    return result


def request_confirmation_focus(window, record):
    """Use the original public UIComponent setter; verify on a later tick."""
    before = confirmation_observation(window)
    if before is None or not before['protected'] or not before['input_visible']:
        raise RuntimeError('visible original protected input required for focus')
    record('p04j_confirmation_focus', phase='request', inventory_id=before['inventory_id'],
        checker_owner_id=before['checker_owner_id'], previous_focus=before['input_focus'],
        requested_focus=1, source='UIComponent.focused public setter620',
        control_numbers_changed=False, submit_enabled_changed=False)
    window.flashObject.inputChecker.textInput.focused = 1


def confirmation_focus_ready(window, record):
    observed = confirmation_observation(window)
    if observed is None:
        return False
    record('p04j_confirmation_focus', phase='readback', inventory_id=observed['inventory_id'],
        checker_owner_id=observed['checker_owner_id'], input_focus=observed['input_focus'],
        source='UIComponent.focused public getter', later_native_tick=True)
    return observed['input_focus'] > 0


def enter_confirmation_text(window, text, record):
    """Set actual UI text, then let the original native KEY_UP handler validate.

    KEY_LEFTARROW moves the caret without submitting. Flash computes and dispatches
    its own Boolean; Python observes it without calling sendUserInputS itself.
    """
    import BigWorld
    import GUI
    import Keys
    if text not in ('100', '0'):
        raise ValueError('bounded diagnostic confirmation input required')
    before = confirmation_observation(window)
    if before is None or not before['protected'] or not before['input_visible']:
        raise RuntimeError('original protected input must be visible')
    if before['input_focus'] <= 0:
        raise RuntimeError('original protected text input must already own native focus')
    info = _dismiss_guard.windows[window]
    if info.get('pending_input') is not None:
        raise RuntimeError('previous native input callback remains pending')
    checker = window.flashObject.inputChecker
    checker.textInput.text = text
    checker.textInput.validateNow()
    actual, valid = checker.getUserText(), checker.isValidControlInput
    if actual != text or type(valid) is not bool:
        raise RuntimeError('original input parser readback differs')
    info['pending_input'] = dict(text=text, callback_offset=len(info.get('input_callbacks', [])),
        return_offset=len(info.get('input_callback_returns', [])),
        setter_offset=len(info.get('input_validation_setters', [])))
    record('p04j_confirmation_input', inventory_id=before['inventory_id'], text=text,
        original_flash_callback='InputChecker.userInputHandler -> InputCheckerMeta.sendUserInputS',
        native_syntax_valid=valid, validation_semantics='control_value_match',
        syntax_source='InputChecker.isValidControlInput', physical_keyboard_input=False,
        callback_boolean_supplied=False, checker_owner_id=before['checker_owner_id'],
        formatted_control_text=checker.formattedControlText, input_focus=before['input_focus'])
    left_key = integer(Keys.KEY_LEFTARROW, 1, 65535)
    return_key = integer(Keys.KEY_RETURN, 1, 65535)
    if not callable(BigWorld.KeyEvent) or not callable(GUI.handleKeyEvent):
        raise RuntimeError('original native input constructors and dispatcher required')
    record('p04j_native_input_api', left_name='KEY_LEFTARROW', left_key=left_key,
        return_name='KEY_RETURN', return_key=return_key,
        key_constructor_type=type(BigWorld.KeyEvent).__name__, key_constructor_callable=True,
        dispatcher_type=type(GUI.handleKeyEvent).__name__, dispatcher_callable=True,
        symbol_source='scripts/client/gui/shared/utils/key_mapping.py',
        symbol_source_sha256='940d65e05aef49045491f5bd2e8ae81d750853f259a05c99e9645b4f87034d4e')
    events = [BigWorld.KeyEvent(left_key, repeat, 0, None, (0, 0)) for repeat in (0, -1)]
    for event, down in zip(events, (True, False)):
        if event.key != left_key or event.isKeyDown() is not down:
            raise RuntimeError('native input key constructor readback differs')
    for event, down in zip(events, (True, False)):
        record('p04j_validation_key_input', phase='dispatch', inventory_id=before['inventory_id'],
            dialog_owner_id=id(window), checker_owner_id=before['checker_owner_id'],
            key=int(event.key), key_name='KEY_LEFTARROW', key_down=down, text=text,
            source='BigWorld.KeyEvent -> GUI.handleKeyEvent', physical_input=False)
        result = GUI.handleKeyEvent(event)
        record('p04j_validation_key_input', phase='return', inventory_id=before['inventory_id'],
            key=int(event.key), key_name='KEY_LEFTARROW', key_down=down, text=text,
            handled=result if type(result) in (bool, int) else None,
            result_type=type(result).__name__, physical_input=False)


def confirmation_input_complete(window, record):
    info = _dismiss_guard.windows[window]
    pending = info.get('pending_input')
    if pending is None:
        return True
    callbacks = info.get('input_callbacks', [])[pending['callback_offset']:]
    returns = info.get('input_callback_returns', [])[pending['return_offset']:]
    setters = info.get('input_validation_setters', [])[pending['setter_offset']:]
    if len(callbacks) > 1 or len(returns) > 1 or len(setters) > 2:
        raise RuntimeError('native validation callback count or actual value differs')
    if not callbacks or not returns or len(setters) < 2:
        return False
    if len(callbacks) != 1 or returns != callbacks or callbacks[0]['value'] != pending['text']:
        raise RuntimeError('native validation callback count or actual value differs')
    valid, owner = callbacks[0]['native_callback_valid'], callbacks[0]['checker_owner_id']
    expected = [dict(phase=phase, value=valid, checker_owner_id=owner, daapi_inited=True)
                for phase in ('call', 'return')]
    if setters != expected:
        raise RuntimeError('original native validation setter chain differs')
    record('p04j_confirmation_input_callback', inventory_id=info['inventory_id'],
        text=pending['text'], native_callback_valid=callbacks[0]['native_callback_valid'],
        checker_owner_id=callbacks[0]['checker_owner_id'], passive=True,
        callback_boolean_supplied=False)
    info['last_input_callback'] = dict(callbacks[0])
    info['last_input_evidence'] = dict(text=pending['text'], native_callback_valid=valid,
        original_meta_value=valid, checker_owner_id=owner,
        original_callback_returned=True, original_meta_returned=True)
    info['pending_input'] = None
    return True


def require_source_validation(observation, text, accepted):
    """Require native callback and original Meta completion, not cached flags."""
    evidence = observation.get('source_bound_validation')
    expected = dict(text=text, native_callback_valid=accepted, original_meta_value=accepted,
        checker_owner_id=observation['checker_owner_id'],
        original_callback_returned=True, original_meta_returned=True)
    if (type(evidence) is not dict or evidence != expected or observation['input_text'] != text
            or any(type(evidence[key]) is not bool for key in ('native_callback_valid',
                'original_meta_value', 'original_callback_returned', 'original_meta_returned'))):
        raise RuntimeError('source-bound native confirmation validation differs')


class _Screenshots(recruitment._Screenshots):
    def capture(self, name, record):
        allowed = ('p04j_preflight_initial', 'p04j_preflight_protected', 'p04j_preflight_wrong',
                   'p04j_preflight_correct', 'p04j_preflight_simple', 'p04j_preflight_final',
                   'p04j_bridge_window_3', 'p04j_bridge_window_5', 'p04j_failure_window',
                   'p04j_relogin_ms1', 'p04j_relogin_is7', 'p04j_dismiss_wrong_input',
                   'p04j_dismiss_confirm_3', 'p04j_dismiss_confirm_5', 'p04j_hire_window_11')
        allowed += tuple('p04j_' + step[0] for step in STEPS)
        if name not in allowed:
            raise ValueError('unsupported dismissal screenshot basename')
        if name not in self.requested:
            if any(entry.startswith(name + '_') for entry in self._entries()):
                raise ValueError('dismissal screenshot basename occupied')
            import BigWorld
            self.requested.add(name)
            BigWorld.screenShot('png', name)
            record('p04j_dismissal_screenshot_requested', basename=name, writer='BigWorld.screenShot')
        names = [entry for entry in self._entries() if re.match(r'\A' + re.escape(name) + r'_[0-9]{3,10}\.png\Z', entry)]
        if not names:
            return None
        if len(names) != 1:
            raise ValueError('ambiguous native dismissal screenshot')
        from project_preferences import owned
        from ms1_crew_scenario import png_evidence
        path = owned(os.path.join(self.directory, names[0]), self.directory)
        if not os.path.isfile(path) or os.path.islink(path):
            raise ValueError('native dismissal screenshot must be owned regular file')
        return png_evidence(path, name)


class _PreflightScenario(transfer.NativeScenario):
    def __init__(self, record, mode, expected, hire=None, settings=None, clock=None):
        global _scenario
        if crew_vehicles.enabled():
            raise RuntimeError('P04J evidence scenarios are MS-1/IS-7 only; unavailable with CREW-ANY')
        if not callable(record) or mode != 'preflight' or hire is not None:
            raise ValueError('only the explicit confirmation-only preflight is currently enabled')
        self.expected = checked_expected(expected, ROLE_LEVEL)
        if (sorted(member_map(self.expected)) != list(range(1, 11))
                or self.expected['ms1_crew'] != [4, 5] or self.expected['is7_crew'] != [6, 7, 8, 10, 9]
                or self.expected['free_quota'] != 6
                or member_row(self.expected, 3)['skills'] != ['repair']
                or member_row(self.expected, 3)['last_skill_level'] != 0
                or member_row(self.expected, 5)['role_level'] != 50):
            raise ValueError('preflight requires the unchanged accepted I roster')
        self.record, self.mode = record, mode
        self.clock = clock if clock is not None else time.monotonic if hasattr(time, 'monotonic') else time.clock
        self.started = self.clock()
        self.last_time, self.advances, self.phase = self.started, 0, 'wait_hangar'
        self.error, self.pending, self.snapshot, self.ammo = None, None, None, None
        self.failure_window, self.failure_capture_started = None, None
        self.ready_since, self.selected, self.selection_ready = None, 1, None
        self.captures, self.cancelled, self.window_identity = [], [], 3
        self.screenshots = None if settings is None else _Screenshots(settings)
        if _scenario is not None and _scenario.phase not in ('complete', 'error'):
            raise RuntimeError('one dismissal diagnostic permitted')
        _scenario = self

    def advance(self, ready_hangar):
        if type(ready_hangar) is not bool:
            raise ValueError('explicit native Hangar readiness required')
        if self.phase == 'complete':
            return True
        if self.phase == 'error':
            raise RuntimeError('failed dismissal diagnostic cannot resume')
        try:
            now = self.clock()
            if (type(now) not in (int, float) or math.isnan(now) or math.isinf(now)
                    or now < self.last_time or now - self.started > 180):
                raise RuntimeError('finite native dismissal deadline180s exceeded')
            self.last_time, self.advances = now, self.advances + 1
            if self.advances > 600:
                raise RuntimeError('native dismissal observation budget exhausted')
            if self.error is not None:
                if self.failure_window is not None and self.screenshots is not None:
                    if self.failure_capture_started is None:
                        self.failure_capture_started = now
                        self.emit('p04j_dismissal_failure_surface',
                                  surface=diagnostic_flash_surface(self.failure_window),
                                  original_error=self.error, acceptance='FAIL')
                    if now - self.failure_capture_started < 5:
                        capture = self.screenshots.capture('p04j_failure_window', self.record)
                        if capture is None:
                            return False
                        self.captures.append(capture)
                        self.emit('p04j_dismissal_screenshot', screenshot=capture, acceptance='FAIL')
                raise RuntimeError(self.error)
            return self._advance(ready_hangar)
        except Exception:
            self.phase = 'error'
            raise

    def emit(self, event, **fields):
        fields.update(version=VERSION, policy=POLICY, mode=self.mode)
        if 'snapshot' in fields:
            fields.update(native_descriptor_parse_repack=True, native_descriptor_count=len(fields['snapshot']['tankmen']))
        self.record(event, **fields)

    def _capture(self, name):
        if self.last_time - self.ready_since > 20:
            raise RuntimeError('dismissal screenshot deadline20s exceeded')
        if self.last_time - self.ready_since < 2:
            return False
        capture = None if self.screenshots is None else self.screenshots.capture(name, self.record)
        if self.screenshots is not None and capture is None:
            return False
        if capture is not None:
            self.captures.append(capture)
            self.emit('p04j_dismissal_screenshot', screenshot=capture)
        return True

    def _assert_unchanged(self):
        if native_snapshot(ROLE_LEVEL) != self.snapshot or cross.native_ammunition() != self.ammo:
            raise RuntimeError('persistent state changed during confirmation-only preflight')

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
            raise RuntimeError('original native Hangar required')
        if Waiting.isVisible():
            return False
        personal = manager.getContainer(ViewTypes.WINDOW).getView(
            criteria={POP_UP_CRITERIA.VIEW_ALIAS: VIEW_ALIAS.PERSONAL_CASE})
        dialog = _dismiss_guard.current
        if self.phase == 'wait_hangar':
            page.tankCarousel.vehicleChange(1)
            self.phase = 'wait_selection'
            self.emit('p04j_dismissal_select', vehicle=1, original_callback='TankCarousel.vehicleChange')
            return False
        if g_currentVehicle.invID != 1:
            if self.phase == 'wait_selection':
                self.selection_ready = None
                return False
            raise RuntimeError('native vehicle changed during dismissal preflight')
        if self.phase == 'wait_selection':
            if self.selection_ready is None:
                self.selection_ready = self.last_time
            if self.last_time - self.selection_ready < 2:
                return False
            self.snapshot, self.ammo = native_snapshot(ROLE_LEVEL), cross.native_ammunition()
            if self.snapshot != dict(self.expected, selected_inventory_id=1):
                raise RuntimeError('preflight starting snapshot differs')
            self.emit('p04j_preflight_before', snapshot=self.snapshot, ammunition=self.ammo)
            self.phase, self.ready_since = 'initial_capture', self.last_time
        self._assert_unchanged()
        if self.phase == 'initial_capture':
            if not self._capture('p04j_preflight_initial'):
                return False
            self.phase = 'open_personal'
        if self.phase == 'open_personal':
            if personal is not None or dialog is not None:
                raise RuntimeError('unexpected window before original PersonalCase')
            page.crewPanel.openPersonalCase(self.window_identity, 2)
            self.phase = 'wait_personal'
            self.emit('p04j_personal_open', inventory_id=self.window_identity, original_callback='Crew.openPersonalCase')
            return False
        if self.phase == 'wait_personal':
            if personal is None or personal.flashObject is None:
                return False
            if type(personal) is not _personal_guard.window_class or personal.tmanInvID != self.window_identity:
                raise RuntimeError('unexpected original PersonalCase')
            _personal_guard.mask(personal)
            model = _personal_guard.models[personal]
            if not all(key in model for key in ('common', 'skills', 'dossier')):
                return False
            if self.window_identity == 5 and model.get('can_learn') is not False:
                raise RuntimeError('ordinary50% learning must remain unavailable')
            personal.dismissTankman(self.window_identity)
            self.phase = 'wait_dialog'
            return False
        if self.phase == 'input_focus':
            if dialog is None:
                raise RuntimeError('original dialog disappeared while focusing input')
            if not confirmation_focus_ready(dialog, self.record):
                if self.last_time - self.ready_since >= 3:
                    self.emit('p04j_dismissal_input_failure_surface',
                              surface=diagnostic_flash_surface(dialog), acceptance='FAIL')
                    raise RuntimeError('original text input focus did not settle within three seconds')
                return False
            enter_confirmation_text(dialog, self.input_text, self.record)
            self.phase = 'wrong_capture' if self.input_text == '100' else 'correct_capture'
            self.ready_since = self.last_time
            return False
        if self.phase in ('wait_dialog', 'protected_capture', 'wrong_capture', 'correct_capture', 'simple_capture'):
            if dialog is None:
                return False
            info = _dismiss_guard.windows[dialog]
            if info.get('pending_input') is not None:
                if not confirmation_input_complete(dialog, self.record):
                    if self.last_time - self.ready_since >= 3:
                        self.emit('p04j_dismissal_input_failure_surface',
                                  surface=diagnostic_flash_surface(dialog), acceptance='FAIL')
                        raise RuntimeError('original native KEY_UP validation callback did not arrive')
                    return False
            if not info.get('surface_captured'):
                if 'surface_capture_started' not in info:
                    info['surface_capture_started'] = self.last_time
                    self.ready_since = self.last_time
                    self.emit('p04j_dismissal_surface', inventory_id=self.window_identity,
                              surface=diagnostic_flash_surface(dialog),
                              daapi_inited=bool(dialog._isDAAPIInited()), acceptance='DIAGNOSTIC_ONLY')
                if not self._capture('p04j_bridge_window_' + str(self.window_identity)):
                    return False
                info['surface_captured'] = True
            observed = confirmation_observation(dialog)
            if observed is None:
                return False
            if observed['inventory_id'] != self.window_identity:
                raise RuntimeError('unexpected original dismissal member')
            if self.phase in ('wrong_capture', 'correct_capture'):
                self.emit('p04j_confirmation_readback', stage=self.phase.split('_', 1)[0],
                          observation=observed, original_callback=info.get('last_input_callback'),
                          before_assertion=True)
            if self.phase == 'wait_dialog':
                if self.window_identity == 3:
                    if (not observed['protected'] or not observed['input_visible']
                            or observed['original_control'] != '0'):
                        raise RuntimeError('protected learned0 confirmation initial state differs')
                    following = 'protected_capture'
                else:
                    if observed['protected'] or observed['input_visible']:
                        raise RuntimeError('simple50 confirmation initial state differs')
                    following = 'simple_capture'
                self.emit('p04j_confirmation_observed', stage='initial', observation=observed, snapshot=self.snapshot)
                self.phase, self.ready_since = following, self.last_time
                return False
            if self.phase == 'wrong_capture':
                require_source_validation(observed, '100', False)
            if self.phase == 'correct_capture':
                require_source_validation(observed, '0', True)
            name = 'p04j_preflight_' + self.phase.split('_', 1)[0]
            if not self._capture(name):
                return False
            self.emit('p04j_confirmation_observed', stage=self.phase.split('_', 1)[0], observation=observed,
                      snapshot=self.snapshot)
            if self.phase in ('protected_capture', 'wrong_capture'):
                self.input_text = '100' if self.phase == 'protected_capture' else '0'
                request_confirmation_focus(dialog, self.record)
                self.phase = 'input_focus'
                self.ready_since = self.last_time
                return False
            # Preflight never submits. Original close resolves the original
            # confirmation as cancel, even after correct input enabled submit.
            dialog.onWindowClose()
            self.cancelled.append(self.window_identity)
            self.emit('p04j_confirmation_cancel', inventory_id=self.window_identity,
                      original_callback='SimpleDialog.onWindowClose', submit_called=False)
            self.phase = 'wait_cancel'
            return False
        if self.phase == 'wait_cancel':
            if dialog is not None:
                return False
            if personal is not None:
                personal.onWindowClose()
                return False
            if self.window_identity == 3:
                self.window_identity, self.phase = 5, 'open_personal'
            else:
                self.phase, self.ready_since = 'final_capture', self.last_time
            return False
        if self.phase == 'final_capture':
            if not self._capture('p04j_preflight_final'):
                return False
            self.emit('p04j_dismissal_preflight', snapshot=self.snapshot, ammunition=self.ammo,
                      cancelled=list(self.cancelled), native_mutations=0, submit_called=False,
                      physical_pointer_input=False, action='original_confirmation_cancel_only',
                      boolean_readback='UNAVAILABLE_OBSERVED', pixels_require_independent_review=True)
            self.phase = 'complete'
            return True
        return False


STEPS = (
    ('dismiss_learned_3', 306, [3, 0, 0]),
    ('dismiss_seated_5', 306, [5, 0, 0]),
    ('hire_driver_11', 309, [3, 1, 1, 0]),
    ('seat_learned_2', 105, [1, 1, 2]),
    ('unload_learned_2', 105, [1, 1, -1]),
    ('restore_driver_11', 105, [1, 1, 11]))
BUTTON_PIN = ('scripts/client/gui/Scaleform/daapi/view/dialogs/SimpleDialog.py',
              56, '696f4e2b6d374d6380ef1a45b02b859fd6c4e2c6726c689db7832e0779a74d74')


def checked_hire(row):
    expected = dict(inventory_id=11, vehicle_inventory_id=1, slot=1, nation_id=0,
                    vehicle_type_id=13, role='driver', role_level=50, skills=[],
                    last_skill_level=0, free_xp=0, dossier_bytes=6,
                    dossier_sha256=DOSSIER_SHA256,
                    sha256='c44ce9409466baed3c5aebea0913b46dbd43dc4ffb27ea6e592df5da800d317a')
    if type(row) is not dict or set(row) != ROW_FIELDS or row != expected:
        raise ValueError('exact precomputed source-bound native driver11 row required')
    for key in ('inventory_id', 'vehicle_inventory_id', 'slot', 'nation_id', 'vehicle_type_id',
                'role_level', 'last_skill_level', 'free_xp', 'dossier_bytes'):
        if type(row[key]) not in recruitment.integer_types:
            raise ValueError('strict integer hire field required')
    return copy.deepcopy(row)


def projected_dismiss(snapshot, identity):
    value = checked_expected(snapshot, ROLE_LEVEL)
    member_row(value, identity)
    value['tankmen'] = [row for row in value['tankmen'] if row['inventory_id'] != identity]
    for key in ('ms1_crew', 'is7_crew'):
        value[key] = [None if member == identity else member for member in value[key]]
    return checked_expected(value, ROLE_LEVEL)


def projected_hire(snapshot, row):
    value, row = checked_expected(snapshot, ROLE_LEVEL), checked_hire(row)
    if (sorted(member_map(value)) != [1, 2, 4, 6, 7, 8, 9, 10]
            or value['free_quota'] != 6 or value['ms1_crew'] != [4, None]):
        raise ValueError('exact two-dismissal state required before monotonic hire11')
    value['tankmen'].append(row)
    value['ms1_crew'][1] = 11
    value['free_quota'] -= 1
    _assignments(value)
    return checked_expected(value, ROLE_LEVEL)


def retired_absence(snapshot):
    from gui.shared import g_itemsCache
    retired = [identity for identity in (3, 5) if identity not in member_map(snapshot)]
    for identity in retired:
        if g_itemsCache.items.getTankman(identity) is not None:
            raise RuntimeError('dismissed identity remains in original native item cache')
    return retired


class NativeCommandTracker(progression.NativeCommandTracker):
    def __init__(self, command, layout):
        if (command not in (105, 306, 309) or type(layout) is not list
                or len(layout) != (4 if command == 309 else 3)
                or any(type(value) not in recruitment.integer_types for value in layout)):
            raise ValueError('one exact native dismissal/hire/transfer layout required')
        self.command, self.layout = command, list(layout)
        self.request, self.update, self.success = None, None, None

    def observe(self, fields):
        if fields.get('event') == 'p04j_native_dismissal_request':
            fields = dict(fields, event='p04i_native_progression_request')
        return progression.NativeCommandTracker.observe(self, fields)


def send_engine_return(window, stage, record):
    """Generate an actual native key event and use the original GUI input path."""
    import BigWorld
    import GUI
    import Keys
    if stage not in ('wrong', 'correct', 'simple'):
        raise ValueError('bounded original confirmation input stage required')
    state = confirmation_observation(window)
    if state is None:
        raise RuntimeError('original confirmation unavailable before engine input')
    if stage in ('wrong', 'correct'):
        require_source_validation(state, '100' if stage == 'wrong' else '0', stage == 'correct')
    elif state['protected'] or state['input_visible'] or state['display_fields']['roleLevel'] != 50:
        raise RuntimeError('original simple50 confirmation differs before engine input')
    focused = window.flashObject.secondBtn.focused
    if (type(focused) not in recruitment.integer_types + (float,) or math.isnan(focused)
            or math.isinf(focused) or int(focused) != focused or focused < 0):
        raise RuntimeError('bounded original button focus observation required')
    key = integer(Keys.KEY_RETURN, 1, 65535)
    if not callable(BigWorld.KeyEvent) or not callable(GUI.handleKeyEvent):
        raise RuntimeError('source-bound original native key constructor and dispatcher required')
    events = [BigWorld.KeyEvent(key, repeat, 0, None, (0, 0)) for repeat in (0, -1)]
    for event, down in zip(events, (True, False)):
        if event.key != key or event.isKeyDown() is not down:
            raise RuntimeError('native key constructor readback differs')
    for event, down in zip(events, (True, False)):
        record('p04j_engine_key_input', stage=stage, phase='dispatch',
               inventory_id=state['inventory_id'], dialog_owner_id=id(window),
               key=int(event.key), key_name='KEY_RETURN', key_down=down,
               cached_submit_enabled=state['raw_boolean_observations']['submit_enabled'],
               submit_focus_observed=int(focused), boolean_readback='UNAVAILABLE_OBSERVED',
               source_bound_validation=state['source_bound_validation'],
               source='BigWorld.KeyEvent -> GUI.handleKeyEvent', physical_input=False)
        result = GUI.handleKeyEvent(event)
        record('p04j_engine_key_input', stage=stage, phase='return',
               inventory_id=state['inventory_id'], dialog_owner_id=id(window),
               key=int(event.key), key_name='KEY_RETURN', key_down=down,
               handled=result if type(result) in (bool, int) else None,
               result_type=type(result).__name__, physical_input=False)


def focus_confirmation_submit(window, record):
    if _dismiss_guard is None or window not in _dismiss_guard.windows:
        raise RuntimeError('original dismissal window required for button focus')
    record('p04j_submit_focus_requested', dialog_owner_id=id(window),
        inventory_id=_dismiss_guard.windows[window]['inventory_id'], button_id='submit',
        original_callback='SimpleDialogMeta.as_setButtonFocusS', enabled_changed=False)
    window.as_setButtonFocusS('submit')


def recruit_window_evidence(window, snapshot):
    flash = window.flashObject
    if flash is None or _recruit_guard is None or not _recruit_guard._window_ok(window):
        raise RuntimeError('source-bound original recruitment window required')
    for name in ('btnAcademy', 'btnScool'):
        button = getattr(flash, name)
        if button.visible is not False or button.enabled is not False or button.type != 'free':
            raise RuntimeError('unsupported paid recruitment control differs')
    free = flash.btnCourses
    if (free.visible is not True or free.enabled is not True or free.type != 'free'
            or free.typeSwitcher.visible is not False or free.typeLabel.text != roster.LABEL % snapshot['free_quota']
            or flash.btnRecruit.enabled is not True):
        raise RuntimeError('native hire quota/button differs')
    return dict(vehicle=window._currentVehicleInvId, slot=int(window._initData['slot']),
                role=window._initData['roleType'], role_level=50, tariff=0,
                free_quota=snapshot['free_quota'], label=free.typeLabel.text,
                paid_controls_hidden=True, original_window_title_preserved=True)


class NativeScenario(_PreflightScenario):
    def __init__(self, record, mode, expected, hire=None, settings=None, clock=None):
        global _scenario
        if mode in ('preflight', 'dismiss'):
            self.hire = checked_hire(hire) if mode == 'dismiss' else None
            if mode == 'preflight' and hire is not None:
                raise ValueError('preflight cannot carry mutation catalog')
            _PreflightScenario.__init__(self, record, 'preflight', expected, settings=settings, clock=clock)
        elif mode == 'relogin':
            if not callable(record) or hire is not None:
                raise ValueError('read-only relogin cannot carry hire data')
            self.expected = checked_expected(expected, ROLE_LEVEL)
            if (sorted(member_map(self.expected)) != [1, 2, 4, 6, 7, 8, 9, 10, 11]
                    or self.expected['ms1_crew'] != [4, 11]
                    or self.expected['is7_crew'] != [6, 7, 8, 10, 9] or self.expected['free_quota'] != 5):
                raise ValueError('relogin requires exact completed sparse roster')
            self.record, self.hire = record, None
            self.clock = clock if clock is not None else time.monotonic if hasattr(time, 'monotonic') else time.clock
            self.started = self.clock()
            self.last_time, self.advances, self.phase = self.started, 0, 'wait_hangar'
            self.error, self.pending, self.snapshot, self.ammo = None, None, None, None
            self.failure_window, self.failure_capture_started = None, None
            self.ready_since, self.selected, self.selection_ready = None, 3 - self.expected['selected_inventory_id'], None
            self.captures, self.cancelled, self.window_identity = [], [], None
            self.screenshots = None if settings is None else _Screenshots(settings)
            if _scenario is not None and _scenario.phase not in ('complete', 'error'):
                raise RuntimeError('one dismissal diagnostic permitted')
            _scenario = self
        else:
            raise ValueError('explicit dismissal diagnostic mode required')
        self.mode, self.step = mode, 0
        self.preflight_active = mode == 'dismiss'
        self.engine_input, self.button_events, self.views = None, [], []

    def emit(self, event, **fields):
        fields['step'] = self.step
        _PreflightScenario.emit(self, event, **fields)

    def _advance(self, ready):
        if self.mode == 'preflight':
            return _PreflightScenario._advance(self, ready)
        if self.preflight_active:
            if not _PreflightScenario._advance(self, ready):
                return False
            self.preflight_active, self.phase = False, 'action'
            return False
        return self._operations(ready)

    def _operations(self, ready):
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
            raise RuntimeError('original native Hangar required')
        if Waiting.isVisible():
            return False
        windows = manager.getContainer(ViewTypes.WINDOW)
        personal = windows.getView(criteria={POP_UP_CRITERIA.VIEW_ALIAS: VIEW_ALIAS.PERSONAL_CASE})
        recruit = windows.getView(criteria={POP_UP_CRITERIA.VIEW_ALIAS: VIEW_ALIAS.RECRUIT_WINDOW})
        dialog = _dismiss_guard.current
        if self.phase == 'wait_hangar':
            page.tankCarousel.vehicleChange(self.selected)
            self.phase = 'wait_selection'
            self.emit('p04j_dismissal_select', vehicle=self.selected, original_callback='TankCarousel.vehicleChange')
            return False
        if g_currentVehicle.invID != self.selected:
            if self.phase == 'wait_selection':
                self.selection_ready = None
                return False
            raise RuntimeError('native selected vehicle changed during dismissal')
        if self.phase == 'wait_selection':
            if self.selection_ready is None:
                self.selection_ready = self.last_time
            if self.last_time - self.selection_ready < 2:
                return False
            actual, ammo = native_snapshot(ROLE_LEVEL), cross.native_ammunition()
            if (actual != dict(self.expected, selected_inventory_id=self.selected)
                    or self.ammo is not None and self.ammo != ammo):
                raise RuntimeError('relogin selection changed persistent state')
            self.snapshot, self.ammo = actual, ammo
            self.phase, self.ready_since = 'relogin_capture', self.last_time
        if self.phase == 'relogin_capture':
            self._assert_unchanged()
            if not self._capture('p04j_relogin_' + ('ms1' if self.selected == 1 else 'is7')):
                return False
            self.views.append(self.selected)
            self.emit('p04j_dismissal_relogin_view', snapshot=self.snapshot, ammunition=self.ammo,
                      readiness=native_readiness(self.snapshot), efficiency=native_efficiency(self.snapshot),
                      retired_absent=retired_absence(self.snapshot), vehicle=self.selected)
            if len(self.views) == 1:
                self.selected, self.selection_ready, self.phase = self.expected['selected_inventory_id'], None, 'wait_selection'
                page.tankCarousel.vehicleChange(self.selected)
                self.emit('p04j_dismissal_select', vehicle=self.selected, original_callback='TankCarousel.vehicleChange')
                return False
            self.emit('p04j_dismissal_relogin', snapshot=self.snapshot, ammunition=self.ammo,
                      readiness=native_readiness(self.snapshot), efficiency=native_efficiency(self.snapshot),
                      retired_absent=retired_absence(self.snapshot), vehicles_observed=self.views,
                      operations=0, action='read_only', exact_snapshot_match=True)
            self.phase = 'complete'
            return True
        if self.phase == 'action':
            self._assert_unchanged()
            if any(window is not None for window in (personal, recruit, dialog)):
                raise RuntimeError('unexpected window before bounded native operation')
            name, command, layout = STEPS[self.step]
            expected = (projected_dismiss(self.snapshot, layout[0]) if command == 306 else
                        projected_hire(self.snapshot, self.hire) if command == 309 else
                        projected_transfer(self.snapshot, *layout))
            self.pending = dict(tracker=NativeCommandTracker(command, layout), expected=expected)
            self.button_events, self.engine_input = [], None
            self.emit('p04j_dismissal_before', name=name, snapshot=self.snapshot, ammunition=self.ammo,
                      retired_absent=retired_absence(self.snapshot))
            if command == 306:
                self.window_identity = layout[0]
                page.crewPanel.openPersonalCase(self.window_identity, 2)
                self.phase = 'operation_personal'
                self.emit('p04j_personal_open', inventory_id=self.window_identity,
                          original_callback='Crew.openPersonalCase')
            elif command == 309:
                page.crewPanel.onShowRecruitWindowClick(roster.target_data(1, 1), False)
                self.phase = 'operation_recruit'
            else:
                callback, args = ('unloadTankman', [2]) if layout[2] == -1 else ('equipTankman', [layout[2], 1])
                self.phase = 'wait_result'
                self.emit('p04j_dismissal_action', name=name, original_callback='Crew.' + callback,
                          arguments=args, native_cmd=command, layout=layout)
                getattr(page.crewPanel, callback)(*args)
            return False
        if self.phase == 'operation_personal':
            self._assert_unchanged()
            if personal is None or personal.flashObject is None:
                return False
            if type(personal) is not _personal_guard.window_class or personal.tmanInvID != self.window_identity:
                raise RuntimeError('unexpected personal case before native dismissal')
            _personal_guard.mask(personal)
            if not all(key in _personal_guard.models[personal] for key in ('common', 'skills', 'dossier')):
                return False
            personal.dismissTankman(self.window_identity)
            self.phase = 'operation_dialog'
            return False
        if self.phase in ('operation_input_focus', 'operation_validation_wait'):
            self._assert_unchanged()
            if dialog is None:
                raise RuntimeError('original dialog disappeared during native input validation')
            if self.phase == 'operation_input_focus':
                if not confirmation_focus_ready(dialog, self.record):
                    if self.last_time - self.ready_since >= 3:
                        raise RuntimeError('original operation input focus did not settle')
                    return False
                enter_confirmation_text(dialog, self.input_text, self.record)
                self.phase, self.ready_since = 'operation_validation_wait', self.last_time
                return False
            if not confirmation_input_complete(dialog, self.record):
                if self.last_time - self.ready_since >= 3:
                    raise RuntimeError('original operation validation callback did not arrive')
                return False
            focus_confirmation_submit(dialog, self.record)
            self.phase = 'wrong_input' if self.input_text == '100' else 'submit_input'
            self.ready_since = self.last_time
            return False
        if self.phase in ('operation_dialog', 'wrong_input', 'wrong_wait', 'submit_input'):
            self._assert_unchanged()
            if dialog is None:
                return False
            observed = confirmation_observation(dialog)
            if observed is None:
                return False
            if observed['inventory_id'] != self.window_identity:
                raise RuntimeError('unexpected native confirmation identity')
            if self.phase == 'operation_dialog':
                if self.window_identity == 3:
                    if not observed['protected'] or observed['original_control'] != '0':
                        raise RuntimeError('learned0 confirmation must start protected')
                    self.input_text = '100'
                    request_confirmation_focus(dialog, self.record)
                    self.phase = 'operation_input_focus'
                else:
                    if observed['protected'] or observed['input_visible']:
                        raise RuntimeError('simple50 original confirmation differs')
                    focus_confirmation_submit(dialog, self.record)
                    self.phase = 'submit_input'
                self.ready_since = self.last_time
                return False
            if self.phase == 'wrong_input':
                if not self._capture('p04j_dismiss_wrong_input'):
                    return False
                self.engine_input = dict(stage='wrong', inventory_id=3, dialog_owner_id=id(dialog))
                send_engine_return(dialog, 'wrong', self.emit)
                self.phase, self.ready_since = 'wrong_wait', self.last_time
                return False
            if self.phase == 'wrong_wait':
                if self.last_time - self.ready_since < 2:
                    return False
                require_source_validation(observed, '100', False)
                if self.button_events or self.pending['tracker'].request is not None:
                    raise RuntimeError('wrong input produced native confirmation or request')
                self.emit('p04j_confirmation_wrong_blocked', inventory_id=3, dialog_owner_id=id(dialog),
                          observation=observed, snapshot=self.snapshot, button_events=0, native_requests=0)
                self.engine_input = None
                self.input_text = '0'
                request_confirmation_focus(dialog, self.record)
                self.phase, self.ready_since = 'operation_input_focus', self.last_time
                return False
            if not self._capture('p04j_dismiss_confirm_' + str(self.window_identity)):
                return False
            stage = 'correct' if self.window_identity == 3 else 'simple'
            self.emit('p04j_confirmation_observed', stage=stage, observation=observed, snapshot=self.snapshot)
            self.engine_input = dict(stage=stage, inventory_id=self.window_identity, dialog_owner_id=id(dialog))
            self.phase, self.ready_since = 'wait_result', self.last_time
            self.emit('p04j_dismissal_action', name=STEPS[self.step][0], native_cmd=306,
                      layout=STEPS[self.step][2], original_callback='GUI.handleKeyEvent',
                      arguments=['KEY_RETURN', 'down', 'up'], dialog_owner_id=id(dialog),
                      inventory_id=self.window_identity, direct_python_submit=False)
            send_engine_return(dialog, stage, self.emit)
            return False
        if self.phase in ('operation_recruit', 'recruit_capture'):
            self._assert_unchanged()
            if recruit is None or recruit.flashObject is None:
                return False
            if type(recruit) is not _recruit_guard.window_class:
                raise RuntimeError('original RecruitWindow required')
            observation = recruit_window_evidence(recruit, self.snapshot)
            if self.phase == 'operation_recruit':
                self.emit('p04j_dismissal_recruit_window', observation=observation, snapshot=self.snapshot)
                self.phase, self.ready_since = 'recruit_capture', self.last_time
                return False
            if not self._capture('p04j_hire_window_11'):
                return False
            self.phase = 'wait_result'
            args = [0, 13, 'driver', 0, 1]
            self.emit('p04j_dismissal_action', name=STEPS[self.step][0], native_cmd=309,
                      layout=STEPS[self.step][2], original_callback='RecruitWindow.buyTankman', arguments=args)
            recruit.buyTankman(*args)
            return False
        if self.phase == 'wait_result':
            tracker = self.pending['tracker']
            if tracker.command == 306 and self.last_time - self.ready_since > 5 and tracker.request is None:
                raise RuntimeError('actual engine input produced no native dismissal request')
            if tracker.success is None:
                return False
            if tracker.command == 306 and len(self.button_events) != 1:
                raise RuntimeError('native dismissal requires one observed original button callback')
            actual, ammo = native_snapshot(ROLE_LEVEL), cross.native_ammunition()
            if actual != self.pending['expected'] or ammo != self.ammo:
                raise RuntimeError('native operation differs from precomputed authoritative transition')
            self.snapshot = actual
            self.emit('p04j_dismissal_callback', **tracker.receipt())
            self.emit('p04j_dismissal_after', name=STEPS[self.step][0], snapshot=actual, ammunition=ammo,
                      retired_absent=retired_absence(actual), readiness=native_readiness(actual),
                      efficiency=native_efficiency(actual))
            if personal is not None:
                personal.onWindowClose()
            self.phase, self.ready_since = 'after_capture', self.last_time
            return False
        if self.phase == 'after_capture':
            if any(window is not None for window in (personal, recruit, dialog)):
                return False
            self._assert_unchanged()
            if not self._capture('p04j_' + STEPS[self.step][0]):
                return False
            self.step, self.pending, self.engine_input = self.step + 1, None, None
            if self.step == len(STEPS):
                self.emit('p04j_dismissal_final', snapshot=self.snapshot, ammunition=self.ammo,
                          readiness=native_readiness(self.snapshot), efficiency=native_efficiency(self.snapshot),
                          retired_absent=retired_absence(self.snapshot), operations=6, dismissals=2,
                          hires=1, transfers=3, actual_engine_input=True, physical_pointer_input=False)
                self.phase = 'complete'
                return True
            self.phase = 'action'
            return False
        return False
