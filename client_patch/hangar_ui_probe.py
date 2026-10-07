# -*- coding: utf-8 -*-
"""Bounded, explicitly requested #717 original Profile UI diagnostic, version 1.

No authentication, fixture changes, replacement callbacks or automatic quit.
The caller starts this once after a real ready Hangar and cancels before fini.
Native execution/pixels, not the pure helper tests, prove UI compatibility.
"""
import hashlib
import binascii
import json
import math
import os
import re
import struct
import time
import traceback

try:
    integer_types = (int, long)
    string_types = (str, unicode)
except NameError:
    integer_types = (int,)
    string_types = (str,)

VERSION = 1
POLL_SECONDS = 0.5
TOTAL_SECONDS = 180.0
MAX_PNG_BYTES = 16 * 1024 * 1024
ALIASES = ('profileSummaryPage', 'profileAwards', 'profileStatistics',
           'profileTechniquePage')
CLASSES = ('ProfileSummaryPage', 'ProfileAwards', 'ProfileStatistics',
           'ProfileTechniquePage')
STEPS = (('profileSummaryPage', 'profile_ui_01_summary'),
         ('profileAwards', 'profile_ui_02_awards'),
         ('profileStatistics', 'profile_ui_03_statistics'),
         ('profileAwards', 'profile_ui_04_awards'),
         ('profileSummaryPage', 'profile_ui_05_summary'),
         ('hangar', 'profile_ui_06_hangar'))
_probe = None
_vehicle_export_requested = False
VEHICLE_EXPORT_MAX_BYTES = 32 * 1024
VEHICLE_COMPONENTS = ('chassis', 'engine', 'fuelTank', 'radio', 'turret', 'gun')


def _bounded_vehicle_export(vehicle, account_dossier_hex, vehicle_dossier_hex):
    """Validate measured primitive resource data; never construct game bytes."""
    if type(vehicle) is not dict or set(vehicle) != set((
            'type_name', 'type_id', 'type_compact_descr', 'compact_descr_hex',
            'max_health', 'crew_roles', 'components')):
        raise ValueError('unexpected resource descriptor fields')
    if vehicle['type_name'] != 'ussr:IS-7':
        raise ValueError('only the explicitly researched IS-7 is exportable')
    type_id = vehicle['type_id']
    if type(type_id) not in (tuple, list) or len(type_id) != 2:
        raise ValueError('two original type IDs required')
    nation = _integer(type_id[0], 0, 15, 'nationID')
    if _integer(type_id[1], 0, 255, 'vehicleTypeID') != 28:
        raise ValueError('IS-7 type ID differs from original list.xml')
    _integer(vehicle['type_compact_descr'], 1, 2147483647, 'type compact descriptor')
    if vehicle['type_compact_descr'] != (28 << 8) + (nation << 4) + 1:
        raise ValueError('native type compact descriptor is inconsistent')
    if _integer(vehicle['max_health'], 1, 100000, 'maxHealth') != 2150:
        raise ValueError('IS-7 HP differs from original hull and turret resources')
    roles = vehicle['crew_roles']
    allowed_roles = ('commander', 'gunner', 'driver', 'radioman', 'loader')
    if type(roles) not in (tuple, list) or len(roles) != 5:
        raise ValueError('five original IS-7 crew slots required')
    for slot in roles:
        if (type(slot) not in (tuple, list) or not 1 <= len(slot) <= 5 or
                any(role not in allowed_roles for role in slot)):
            raise ValueError('bounded original crew roles required')
    components = vehicle['components']
    if type(components) is not dict or set(components) != set(VEHICLE_COMPONENTS):
        raise ValueError('exactly six original component descriptors required')
    for name in VEHICLE_COMPONENTS:
        item = components[name]
        if type(item) is not dict or set(item) != set(('id', 'compact_descr')):
            raise ValueError('unexpected original component fields')
        item_id = item['id']
        if (type(item_id) not in (tuple, list) or len(item_id) != 2 or
                _integer(item_id[0], 0, 15, 'component nation') != nation):
            raise ValueError('component nation differs from vehicle')
        _integer(item_id[1], 0, 65535, 'component ID')
        _integer(item['compact_descr'], 1, 2147483647, 'component compact descriptor')
    for value, maximum, field in ((vehicle['compact_descr_hex'], 1024, 'vehicle'),
                                   (account_dossier_hex, 8192, 'account dossier'),
                                   (vehicle_dossier_hex, 8192, 'vehicle dossier')):
        if (type(value) not in string_types or not 2 <= len(value) <= maximum or
                len(value) % 2 or re.match(r'\A[0-9a-f]+\Z', value) is None):
            raise ValueError('bounded original hex bytes required: ' + field)
    raw = binascii.unhexlify(vehicle['compact_descr_hex'])
    if len(raw) != 15:
        raise ValueError('original base descriptor requires fifteen bytes')
    values = struct.unpack('<2B6HB', raw)
    if values[:2] != (1 + (nation << 4), 28) or values[-1] != 0:
        raise ValueError('native base descriptor header/flags mismatch')
    kinds = {'chassis': 2, 'engine': 5, 'fuelTank': 6, 'radio': 7, 'turret': 3, 'gun': 4}
    for index, name in enumerate(VEHICLE_COMPONENTS):
        item = components[name]
        if (values[index + 2] != item['id'][1] or
                item['compact_descr'] != (item['id'][1] << 8) + (nation << 4) + kinds[name]):
            raise ValueError('native base descriptor/component mismatch')
    return {'version': 1, 'vehicle': vehicle,
            'account_dossier_hex': account_dossier_hex,
            'vehicle_dossier_hex': vehicle_dossier_hex,
            'origin': 'original VehicleDescr(typeName), original empty dossier builders'}


def _write_vehicle_export(path, payload):
    raw = (json.dumps(payload, ensure_ascii=True, sort_keys=True,
                      separators=(',', ':')) + '\n').encode('ascii')
    if len(raw) > VEHICLE_EXPORT_MAX_BYTES:
        raise ValueError('resource export exceeds bounded JSON size')
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_BINARY', 0)
    descriptor = os.open(path, flags, 0o600)
    with os.fdopen(descriptor, 'wb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    return {'path': path, 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def export_original_vehicle(type_name, record, outdir):
    """Explicit one-shot read of IS-7 resources after a genuine ready Hangar.

    The caller must validate outdir under its owned local root. This function
    writes only one fixed filename exclusively and never selects/grants a tank,
    navigates UI, sends an RPC or writes account/fixture data.
    """
    global _vehicle_export_requested
    if type_name != 'ussr:IS-7' or _vehicle_export_requested:
        raise ValueError('unsupported or repeated original vehicle export')
    from project_preferences import owned
    if not os.path.isabs(outdir) or not os.path.isdir(outdir):
        raise ValueError('existing absolute owned export directory required')
    path = owned(os.path.join(outdir, 'original-vehicle-is7.json'), outdir)
    if os.path.lexists(path):
        raise ValueError('original vehicle export already exists')
    _vehicle_export_requested = True
    try:
        import BigWorld
        import dossiers2
        from items import vehicles
        from CurrentVehicle import g_currentVehicle
        from gui.shared import g_itemsCache
        from ConnectionManager import connectionManager

        def selection():
            player, current = BigWorld.player(), g_currentVehicle.item
            if (player is None or current is None or not connectionManager.isConnected() or
                    not g_itemsCache.isSynced()):
                raise RuntimeError('resource export requires a real connected selected vehicle')
            raw = current.descriptor.makeCompactDescr()
            if not 1 <= len(raw) <= 512:
                raise ValueError('selected descriptor exceeds observation bound')
            return {'database_id': _integer(player.databaseID, 1, 2147483647, 'databaseID'),
                    'selected_inventory_id': _integer(g_currentVehicle.invID, 1, 2147483647, 'inventory ID'),
                    'selected_descriptor_sha256': hashlib.sha256(raw).hexdigest()}

        before = selection()
        native_id = vehicles.g_list.getIDsByName(type_name)
        desc = vehicles.VehicleDescr(typeName=type_name)
        if tuple(desc.type.id) != tuple(native_id) or desc.type.name != type_name:
            raise ValueError('original vehicle lookup/descriptor identity mismatch')
        components = {}
        for name in VEHICLE_COMPONENTS:
            part = getattr(desc, name)
            components[name] = {'id': list(part['id']), 'compact_descr': part['compactDescr']}
        vehicle = {'type_name': desc.type.name, 'type_id': list(desc.type.id),
                   'type_compact_descr': desc.type.compactDescr,
                   'compact_descr_hex': binascii.hexlify(desc.makeCompactDescr()).decode('ascii'),
                   'max_health': desc.maxHealth, 'crew_roles': desc.type.crewRoles,
                   'components': components}
        payload = _bounded_vehicle_export(vehicle,
            binascii.hexlify(dossiers2.getAccountDossierDescr('').makeCompDescr()).decode('ascii'),
            binascii.hexlify(dossiers2.getVehicleDossierDescr('').makeCompDescr()).decode('ascii'))
        after = selection()
        if before != after:
            raise RuntimeError('selected vehicle/account changed during readonly export')
        payload.update(selection_before=before, selection_after=after)
        result = _write_vehicle_export(path, payload)
        record('original_vehicle_export', version=1, type_name=type_name,
               selection_unchanged=True, selection_before=before, selection_after=after,
               output=result)
        return result
    except Exception:
        record('original_vehicle_export_error', version=1, type_name=type_name,
               traceback=traceback.format_exc())
        raise


def _now():
    # On the measured Windows Python 2 runtime clock() is elapsed wall time.
    return time.monotonic() if hasattr(time, 'monotonic') else time.clock()


def _integer(value, lower, upper, field):
    if type(value) not in integer_types or not lower <= value <= upper:
        raise ValueError('bounded integer required: ' + field)
    return value


def summarize_awards_data(data):
    """Summarize the original three-field data without walking rich tooltips.

    Seven catalogue sections can be nonempty at zero battles. Nonzero values
    alone do not mean an earned award: original ClassProgressAchievement uses
    NO_LVL=5. Counters preserve that observation without rewriting the data.
    Only known scalar fields are read; nested dossier/description/icon values
    are neither copied, traversed, formatted nor hashed.
    """
    if type(data) is not dict or len(data) != 3 or set(data) != set((
            'achievementsList', 'totalItemsList', 'battlesCount')):
        raise ValueError('unexpected original Awards data keys')
    battles = _integer(data['battlesCount'], 0, 2147483647, 'battlesCount')
    blocks, totals = data['achievementsList'], data['totalItemsList']
    if (type(blocks) not in (list, tuple) or type(totals) not in (list, tuple) or
            len(blocks) != 7 or len(totals) != 7):
        raise ValueError('Awards requires seven original sections')
    counters = ('packed_items', 'catalog_items', 'in_dossier_items',
                'done_items', 'rare_items', 'nonzero_value_items')
    result = dict((key, 0) for key in counters)
    result.update(version=VERSION, battles_count=battles, section_count=7, sections=[])
    for index, block in enumerate(blocks):
        if type(block) not in (list, tuple) or len(block) > 256:
            raise ValueError('Awards section exceeds bounded catalogue')
        total = _integer(totals[index], 0, 256, 'totalItemsList')
        if len(block) > total:
            raise ValueError('packed Awards exceed unfiltered section count')
        row = dict((key, 0) for key in counters)
        row.update(index=index, packed_items=len(block), catalog_items=total)
        for item in block:
            if type(item) is not dict or len(item) > 32:
                raise ValueError('bounded original achievement dict required')
            for field, counter in (('isInDossier', 'in_dossier_items'),
                                   ('isDone', 'done_items'), ('isRare', 'rare_items')):
                if type(item.get(field)) is not bool:
                    raise ValueError('original achievement boolean required: ' + field)
                row[counter] += int(item[field])
            value = item.get('value')
            if (type(value) not in integer_types + (float,) or
                    not -9007199254740991 <= value <= 9007199254740991 or
                    (type(value) is float and (math.isnan(value) or math.isinf(value)))):
                raise ValueError('bounded original achievement numeric value required')
            row['nonzero_value_items'] += int(value != 0)
        for key in counters:
            result[key] += row[key]
        if result['packed_items'] > 1024 or result['catalog_items'] > 1024:
            raise ValueError('Awards catalogue exceeds total observation bound')
        result['sections'].append(row)
    return result


class StableWindow(object):
    """Pure continuous-readiness/deadline gate; no clock or UI is synthesized."""

    def __init__(self, started, timeout, stable_seconds):
        if not 0 < stable_seconds < timeout <= TOTAL_SECONDS:
            raise ValueError('invalid bounded readiness window')
        self.started, self.deadline = started, started + timeout
        self.stable_seconds, self.ready_since = stable_seconds, None
        self.last_time = started

    def observe(self, now, ready):
        if not isinstance(now, (int, float)) or math.isnan(now) or math.isinf(now):
            raise ValueError('finite monotonic time required')
        if now < self.last_time:
            raise ValueError('monotonic time moved backwards')
        self.last_time = now
        if now >= self.deadline:
            raise RuntimeError('original view did not stabilize before deadline')
        if not ready:
            self.ready_since = None
            return False
        if self.ready_since is None:
            self.ready_since = now
        return now - self.ready_since >= self.stable_seconds


def _context(expected_database_id):
    import BigWorld
    from ConnectionManager import connectionManager
    from gui.WindowsManager import g_windowsManager
    from gui.Scaleform.framework import ViewTypes
    from gui.Scaleform.Waiting import Waiting
    from gui.shared import g_itemsCache
    player = BigWorld.player()
    if player is None or player.databaseID != expected_database_id or not connectionManager.isConnected():
        raise RuntimeError('original Account identity/connection changed during UI scenario')
    if not g_itemsCache.isSynced():
        raise RuntimeError('original Account cache lost sync during UI scenario')
    clan_id, clan_info = g_itemsCache.items.getClanInfo(None)
    dossier = g_itemsCache.items.getAccountDossier(None)
    if (clan_id != 0 or clan_info is not None or
            len(dossier.getBlock('rareAchievements')) != 0 or
            dossier.getTotalStats().getBattlesCount() != 0):
        raise ValueError('account differs from audited fresh-account UI scenario')
    window = g_windowsManager.window
    manager = window.containerManager if window is not None else None
    main = manager.getContainer(ViewTypes.VIEW) if manager is not None else None
    sub = manager.getContainer(ViewTypes.LOBBY_SUB) if manager is not None else None
    return (player, main.getView() if main is not None else None,
            sub.getView() if sub is not None else None, bool(Waiting.isVisible()))


def _navigator(player, page):
    if page is None or type(page).__name__ != 'ProfilePage' or page.settings.alias != 'profile':
        return None
    nav = page.components.get('profileTabNavigator')
    if (nav is None or type(nav).__name__ != 'ProfileTabNavigator' or
            nav.flashObject is None or page.flashObject is None):
        return None
    sections = nav._ProfileTabNavigator__navigatorOwnInitInfo['sectionsData']
    if len(sections) != 4 or tuple(item['alias'] for item in sections) != ALIASES:
        raise ValueError('unexpected original profile tab layout')
    return nav


def _observe(alias, database_id):
    player, lobby, page, waiting = _context(database_id)
    fields = {'alias': alias, 'database_id': player.databaseID, 'observed_ready': False,
              'waiting_visible': waiting, 'owner_id': None, 'owner_class': None}
    if waiting or type(lobby).__name__ != 'LobbyView' or lobby.flashObject is None:
        return fields
    if alias == 'hangar':
        import hangar_bootstrap
        hangar = hangar_bootstrap.observe()
        fields.update(owner_id=id(page) if page is not None else None,
                      owner_class=type(page).__name__ if page is not None else None,
                      flash_bound=page is not None and page.flashObject is not None,
                      vehicle_model_loaded=bool(hangar.get('vehicle_model_loaded')))
        fields['observed_ready'] = bool(
            fields['owner_class'] == 'Hangar' and page.settings.alias == 'hangar' and
            fields['flash_bound'] and fields['vehicle_model_loaded'])
        return fields
    if alias not in ALIASES:
        raise ValueError('unsupported diagnostic profile alias')
    nav = _navigator(player, page)
    if nav is None:
        return fields
    item = nav.components.get(alias)
    fields.update(selected_index=int(nav.flashObject.bar.selectedIndex),
                  owner_id=id(item) if item is not None else None,
                  owner_class=type(item).__name__ if item is not None else None,
                  flash_bound=item is not None and item.flashObject is not None,
                  is_active=bool(item.isActive) if item is not None else False,
                  own_user_id=item._userID is None if item is not None else False,
                  same_database_id=item._databaseID == player.databaseID if item is not None else False,
                  same_name=item._userName == player.name if item is not None else False)
    fields['observed_ready'] = bool(
        fields['selected_index'] == ALIASES.index(alias) and
        fields['owner_class'] == CLASSES[ALIASES.index(alias)] and fields['flash_bound'] and
        fields['is_active'] and fields['own_user_id'] and fields['same_database_id'] and fields['same_name'])
    return fields


class _Probe(object):
    def __init__(self, settings, record):
        self.record, self.settings = record, settings
        self.started, self.callback_id = _now(), None
        self.phase, self.step_index, self.alias = 'initial_hangar', 0, 'hangar'
        self.finished, self.screenshots = False, []
        self.database_id, self.directory = None, None
        # Two seconds of margin let the independent 1 Hz observer measure at
        # least sixty seconds without changing its acceptance threshold.
        self.window = StableWindow(self.started, 67.0, 62.0)
        self.last_observation = None

    def emit(self, event, **fields):
        context = self.state()
        context.update(fields)
        self.record(event, **context)

    def state(self):
        return {'version': VERSION, 'phase': self.phase, 'step_index': self.step_index,
                'alias': self.alias, 'database_id': self.database_id,
                'scenario_elapsed': round(_now() - self.started, 6)}

    def initialize(self):
        import BigWorld
        import Settings
        from project_preferences import owned
        self.database_id = _integer(BigWorld.player().databaseID, 1, 2147483647, 'databaseID')
        self.directory = owned(self.settings['screenshot_dir'], self.settings['local_root'])
        if not os.path.isabs(self.settings['screenshot_dir']) or not os.path.isdir(self.directory):
            raise ValueError('prepared absolute owned screenshot directory required')
        configured = Settings.g_instance.engineConfig.readString('screenShot/path')
        if not os.path.isabs(configured) or owned(configured, self.settings['local_root']) != self.directory:
            raise ValueError('native screenshot path differs from owned scenario directory')
        self.last_observation = _observe('hangar', self.database_id)
        if not self.last_observation['observed_ready']:
            raise RuntimeError('scenario must start after original ready Hangar')
        self.emit('profile_scenario_start', original_ui_only=True, no_automatic_quit=True,
                  initial_hangar_seconds=62, max_seconds=TOTAL_SECONDS,
                  aliases=[step[0] for step in STEPS])
        self.tick()

    def action(self, alias):
        player, lobby, page, waiting = _context(self.database_id)
        if waiting:
            raise RuntimeError('original GUI became waiting before diagnostic action')
        if self.step_index == 1:
            if type(page).__name__ != 'Hangar' or page.settings.alias != 'hangar':
                raise RuntimeError('profile entry must start from original Hangar')
            header = lobby.components['lobbyHeader']
            if type(header).__name__ != 'LobbyHeader' or header.flashObject is None:
                raise RuntimeError('original LobbyHeader is not Flash-bound')
            self.emit('profile_scenario_action', action='open_profile', moment='call',
                      original_handler='LobbyHeader.menuItemClick')
            header.menuItemClick('profile')
        else:
            nav = _navigator(player, page)
            if nav is None:
                raise RuntimeError('original profile navigator absent before transition')
            if alias == 'hangar':
                self.emit('profile_scenario_action', action='close_profile', moment='call',
                          original_handler='ProfilePage.onCloseProfile')
                page.onCloseProfile()
            else:
                index = ALIASES.index(alias)
                before = int(nav.flashObject.bar.selectedIndex)
                if not 0 <= before < 4 or before == index:
                    raise RuntimeError('need a fresh original tab transition')
                self.emit('profile_scenario_action', action='select_section', moment='call',
                          original_flash_setter='ProfileHeaderButtonBar.selectedIndex',
                          selected_index=index, previous_index=before)
                nav.flashObject.bar.selectedIndex = index
        self.emit('profile_scenario_action', moment='return')

    def next_step(self, now):
        self.step_index += 1
        self.alias = STEPS[self.step_index - 1][0]
        self.phase = 'waiting_view'
        self.window = StableWindow(now, 20.0, 5.0 if self.alias == 'hangar' else 2.0)
        self.action(self.alias)

    def request_screenshot(self):
        import BigWorld
        basename = STEPS[self.step_index - 1][1]
        entries = os.listdir(self.directory)
        if len(entries) > 128 or any(entry.startswith(basename + '_') for entry in entries):
            raise ValueError('native scenario screenshot basename is already occupied')
        self.emit('profile_scenario_screenshot_requested', basename=basename,
                  directory=self.directory, writer='BigWorld.screenShot', extension='png')
        BigWorld.screenShot('png', basename)
        self.phase = 'waiting_screenshot'

    def screenshot(self):
        from project_preferences import owned
        basename = STEPS[self.step_index - 1][1]
        entries = os.listdir(self.directory)
        if len(entries) > 128:
            raise ValueError('scenario screenshot directory exceeds bound')
        matches = [entry for entry in entries if re.match(
            r'\A' + re.escape(basename) + r'_[0-9]{3,10}\.png\Z', entry)]
        if not matches:
            return None
        if len(matches) != 1:
            raise ValueError('ambiguous native scenario screenshot output')
        path = owned(os.path.join(self.directory, matches[0]), self.directory)
        if not os.path.isfile(path) or os.path.islink(path):
            raise ValueError('native screenshot is not an owned regular file')
        size = os.path.getsize(path)
        if size > MAX_PNG_BYTES:
            raise ValueError('native screenshot exceeds size bound')
        if size < 20:
            return None
        with open(path, 'rb') as stream:
            signature = stream.read(8)
            stream.seek(-12, 2)
            tail = stream.read(12)
            if signature != b'\x89PNG\r\n\x1a\n' or tail != b'\x00\x00\x00\x00IEND\xaeB`\x82':
                return None
            stream.seek(0)
            payload = stream.read(MAX_PNG_BYTES + 1)
        if len(payload) != size:
            raise ValueError('native screenshot changed while reading')
        return {'basename': basename, 'path': path, 'bytes': size,
                'sha256': hashlib.sha256(payload).hexdigest(), 'visual_review': 'NOT_RUN'}

    def tick(self):
        import BigWorld
        self.callback_id = None
        if self.finished:
            return
        try:
            now = _now()
            if now - self.started >= TOTAL_SECONDS:
                raise RuntimeError('profile scenario exceeded 180 second bound')
            observation = _observe(self.alias, self.database_id)
            if self.phase in ('initial_hangar', 'waiting_view'):
                if (self.last_observation is not None and
                        observation.get('owner_id') != self.last_observation.get('owner_id')):
                    self.window.observe(now, False)
                self.last_observation = observation
                if self.window.observe(now, observation['observed_ready']):
                    stable = round(now - self.window.ready_since, 6)
                    self.emit('profile_scenario_view_ready', stable_seconds=stable,
                              observation=observation)
                    if self.phase == 'initial_hangar':
                        self.next_step(now)
                    else:
                        self.request_screenshot()
            elif self.phase == 'waiting_screenshot':
                if now >= self.window.deadline:
                    raise RuntimeError('native screenshot not completed before step deadline')
                if not observation['observed_ready']:
                    raise RuntimeError('original view changed before screenshot verification')
                if observation['owner_id'] != self.last_observation['owner_id']:
                    raise RuntimeError('original view identity changed during screenshot')
                self.last_observation = observation
                result = self.screenshot()
                if result is not None:
                    self.screenshots.append(result)
                    self.emit('profile_scenario_screenshot', screenshot=result, observation=observation)
                    if self.step_index == len(STEPS):
                        self.phase, self.finished = 'complete', True
                        self.emit('profile_scenario_complete', screenshots=len(self.screenshots),
                                  original_ui_only=True, automatic_quit=False,
                                  native_pixels_review='NOT_RUN')
                        return
                    self.next_step(now)
            else:
                raise RuntimeError('invalid diagnostic scenario phase')
            self.callback_id = BigWorld.callback(POLL_SECONDS, self.tick)
        except Exception:
            self.fail()
            raise

    def fail(self):
        self.finished = True
        self.phase = 'error'
        self.emit('profile_scenario_error', traceback=traceback.format_exc()[-16384:],
                  observation=self.last_observation)


def start(settings, record):
    """Caller must gate this with the consumed explicit ui_scenario='profile'."""
    global _probe
    if _probe is not None:
        raise RuntimeError('only one Profile UI scenario per client process')
    _probe = _Probe(settings, record)
    try:
        _probe.initialize()
    except Exception:
        if not _probe.finished:
            _probe.fail()
        raise


def state():
    """Bounded profiler context only; never returns credentials or GUI data."""
    return _probe.state() if _probe is not None else None


def stop(reason='fini'):
    """Cancel before trace/engine teardown; cancellation is never completion."""
    if reason not in ('fini', 'operator'):
        raise ValueError('unsupported scenario cancellation reason')
    if _probe is None or _probe.finished:
        return
    import BigWorld
    if _probe.callback_id is not None:
        BigWorld.cancelCallback(_probe.callback_id)
        _probe.callback_id = None
    _probe.finished, _probe.phase = True, 'cancelled'
    _probe.emit('profile_scenario_cancelled', reason=reason)
