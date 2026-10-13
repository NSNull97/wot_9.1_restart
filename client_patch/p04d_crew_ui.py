# -*- coding: utf-8 -*-
"""Opt-in #717 RecruitWindow compatibility for one test_lab MS-1 driver.

Install after crew_capabilities allows only open_recruit/recruit and before
BusinessHandler construction. Dispose original GUI before fini(). This replaces
the unsupported tariff reader and guards the original callbacks; it does not
replace a processor, account command, inventory reader or server result.

Source: recruitwindow.pyc ac81a6a0...fc41 and Application.swf 8c53f7cf...b62.
The source-backed Flash bridge/property writes still require native acceptance.
The historical paid tariffs and historical tier-to-level mapping are UNKNOWN.
"""
import hashlib
import math
import os
import re
import time

VERSION = 1
POLICY = 'test_lab.free100.ms1_driver.one_quota.v1'
LABEL = u'Тест: 100%, бесплатно'
EXHAUSTED_LABEL = u'Квота использована'
PENDING_LABEL = u'Повторный запрос закрыт'
NOTICE = (u'Тестовый стенд: доступен один бесплатный водитель МС-1 (100%). '
          u'Платный найм недоступен; исторические тарифы не подтверждены.')
MAX_EVENTS = 128
DRIVER_SHA256 = 'e4c85b2b116b96eff5d68aa8df2e509370f923843def67331478e4b62309b76d'
TARGET_DATA = dict(nationID=0, tankType='lightTank', typeID=13, roleType='driver', slot=1)
_guard = None
try:
    integer_types = (int, long)
    string_types = (str, unicode)
except NameError:
    integer_types = (int,)
    string_types = (str,)


def _integer(value, lower, upper):
    if type(value) not in integer_types or not lower <= value <= upper:
        raise ValueError('bounded native integer required')
    return value


def _number_equals(value, expected):
    # Flash Number is a double; accepting an exact finite integral value here
    # matches the original int() conversion without accepting strings/bools.
    return type(value) in integer_types + (float,) and value == expected


def _target_data(data):
    if type(data) is not dict or len(data) > 64:
        return False
    return (all(_number_equals(data.get(key), value)
                for key, value in (('nationID', 0), ('typeID', 13), ('slot', 1)))
            and data.get('tankType') == 'lightTank' and data.get('roleType') == 'driver')


def _context_ok(ctx):
    return (type(ctx) is dict and len(ctx) <= 16
            and _number_equals(ctx.get('currentVehicleId'), 1)
            and ctx.get('menuEnabled', False) is False and _target_data(ctx.get('data')))


class _Native(object):
    def state(self):
        import BigWorld
        from gui.shared import g_itemsCache
        from CurrentVehicle import g_currentVehicle
        from ConnectionManager import connectionManager
        if BigWorld.player() is None or not connectionManager.isConnected() or not g_itemsCache.isSynced():
            raise RuntimeError('real connected synced Account required for recruitment')
        vehicle = g_itemsCache.items.getVehicle(1)
        if (vehicle is None or vehicle.intCD != 3329 or vehicle.descriptor.type.name != 'ussr:MS-1'
                or tuple(vehicle.descriptor.type.crewRoles[1]) != ('driver',)):
            raise RuntimeError('original MS-1 driver seat is unavailable')
        stats = g_itemsCache.items.stats
        return dict(selected_inventory_id=g_currentVehicle.invID, free_quota=stats.freeTankmenLeft,
                    credits=stats.credits, gold=stats.gold)


class _RecruitGuard(object):
    """Own exact descriptors and at most one submission during this session."""
    def __init__(self, business_class, window_class, messages, record, native=None):
        if not callable(record):
            raise ValueError('recorder required')
        self.business_class, self.window_class = business_class, window_class
        self.messages, self.record = messages, record
        self.native = _Native() if native is None else native
        self.active, self.submitted, self.events = False, False, 0
        self.bindings = []
        replacements = ((business_class, '_BusinessHandler__showRecruitWindow', self._open),
                        (window_class, '_RecruitWindow__getInitialData', self._initial),
                        (window_class, 'buyTankman', self._buy),
                        (window_class, 'onGoldChange', self._refresh),
                        (window_class, 'onCreditsChange', self._refresh),
                        (window_class, 'updateAllDropdowns', self._refresh))
        for cls, name, factory in replacements:
            original = cls.__dict__[name]
            if isinstance(original, (staticmethod, classmethod)) or not callable(original):
                raise TypeError('unexpected original recruitment method descriptor')
            self.bindings.append((cls, name, original, factory(original)))

    def emit(self, event, **fields):
        cleanup = event == 'p04d_recruit_policy' and fields.get('phase') == 'restore'
        if self.events >= MAX_EVENTS and not (cleanup and self.events == MAX_EVENTS):
            raise RuntimeError('recruitment diagnostic event budget exhausted')
        self.events += 1
        fields.update(version=VERSION, policy=POLICY)
        self.record(event, **fields)

    def _state(self):
        if not self.active:
            raise RuntimeError('recruitment callback after cleanup')
        value = self.native.state()
        if type(value) is not dict or set(value) != set(('selected_inventory_id', 'free_quota', 'credits', 'gold')):
            raise ValueError('unexpected native recruitment state shape')
        _integer(value['selected_inventory_id'], -1, 2147483647)
        _integer(value['free_quota'], 0, 1)
        _integer(value['credits'], 0, 9223372036854775807)
        _integer(value['gold'], 0, 9223372036854775807)
        return value

    def _deny(self, reason):
        if not self.active:
            raise RuntimeError('recruitment callback after cleanup')
        self.emit('p04d_recruit_denied', reason=reason, original_callback_called=False)
        if self.messages.g_instance is None:
            raise RuntimeError('original SystemMessages unavailable')
        self.messages.pushMessage(NOTICE, type=self.messages.SM_TYPE.Warning)

    def _open(self, original):
        guard = self
        def open_window(owner, event):
            state = guard._state()
            if not _context_ok(event.ctx) or state['selected_inventory_id'] != 1:
                return guard._deny('unsupported_window_target')
            guard.emit('p04d_recruit_open', original_callback_called=True, native_vehicle_id=1, slot=1)
            return original(owner, event)
        return open_window

    def _window_ok(self, window):
        return (window._currentVehicleInvId == 1 and window._menuEnabled is False
                and _target_data(window._initData))

    def _mask(self, window, state):
        flash = window.flashObject
        if flash is None:
            raise RuntimeError('original RecruitWindow is not Flash-bound')
        # Application.swf TankmanTrainingButton.updatePrice 6..39 short-circuits
        # for type=free before formatting the absent paid price; 217..233 hides
        # both price fields. Hidden paid controls never receive invented prices.
        for button in (flash.btnAcademy, flash.btnScool):
            button.visible = False
            button.enabled = False
            button.type = 'free'
            button.validateNow()
        free = flash.btnCourses
        free.type = 'free'
        free.validateNow()
        free.visible = True
        free.enabled = state['free_quota'] == 1 and not self.submitted
        free.selected = True
        # The original timeline is not evidence of the project policy level.
        # Hide it; set text after native draw (which writes a localized label).
        free.typeSwitcher.visible = False
        free.typeLabel.text = (LABEL if free.enabled else EXHAUSTED_LABEL
                               if state['free_quota'] == 0 else PENDING_LABEL)
        flash.btnRecruit.enabled = free.enabled
        for name in ('nationDropdown', 'vehicleClassDropdown', 'vehicleTypeDropdown', 'roleDropdown'):
            getattr(flash, name).enabled = False

    def _initial(self, original):
        guard = self
        def initial(window):
            state = guard._state()
            if not guard._window_ok(window) or state['selected_inventory_id'] != 1:
                raise RuntimeError('unsupported recruitment window reached initialization')
            guard._mask(window, state)
            # Skip ONLY original __getInitialData, whose unconditional rows1/2
            # reads are incompatible with an honestly disabled paid economy.
            data = dict(credits=state['credits'], gold=state['gold'], data=dict(TARGET_DATA),
                        menuEnabled=False, schoolUpgradeActionPriceData=None,
                        academyUpgradeActionPriceData=None)
            window.flashObject.as_initData(data)
            window.flashObject.validateNow()
            guard._mask(window, state)
            guard.emit('p04d_recruit_window_ready', native_vehicle_id=1, slot=1, free_quota=state['free_quota'],
                       paid_controls_hidden=True, paid_price_keys_present=False,
                       policy_label=LABEL, flash_visual_acceptance='NOT_RUN')
        return initial

    def _refresh(self, original):
        guard = self
        def refresh(window, *args, **kwargs):
            state = guard._state()
            if not guard._window_ok(window):
                return guard._deny('unsupported_window_refresh')
            result = original(window, *args, **kwargs)
            guard._mask(window, state)
            return result
        return refresh

    def _buy(self, original):
        guard = self
        def buy(window, nationID, vehTypeID, role, studyType, slot):
            state = guard._state()
            if (not guard._window_ok(window) or state['selected_inventory_id'] != 1
                    or not _number_equals(nationID, 0) or not _number_equals(vehTypeID, 13)
                    or role != 'driver' or not _number_equals(studyType, 0) or not _number_equals(slot, 1)):
                return guard._deny('unsupported_recruit_target_or_tariff')
            if state['free_quota'] != 1 or guard.submitted:
                return guard._deny('quota_or_session_submission_exhausted')
            guard.emit('p04d_recruit_submit', native_vehicle_id=1, slot=1, tariff=0,
                       original_callback_called=True, original_processor='TankmanRecruitAndEquip', native_cmd=309)
            guard.submitted = True
            guard._mask(window, state)
            # Preserve the exact original decorated generator/callback chain.
            # No local inventory mutation and no synthesized success callback.
            return original(window, nationID, vehTypeID, role, studyType, slot)
        return buy

    def install(self):
        if self.active:
            raise RuntimeError('recruitment policy installed twice')
        for cls, name, original, replacement in self.bindings:
            if cls.__dict__.get(name) is not original:
                raise RuntimeError('recruitment binding changed before install: ' + name)
        self.emit('p04d_recruit_policy', phase='install', historical_paid_tariffs='UNKNOWN',
                  historical_tier_levels='UNKNOWN', original_processor_preserved=True,
                  lifecycle_requirement='before_original_BusinessHandler_construction')
        for cls, name, original, replacement in self.bindings:
            setattr(cls, name, replacement)
        self.active = True

    def restore(self):
        if not self.active:
            return
        for cls, name, original, replacement in self.bindings:
            if cls.__dict__.get(name) is not replacement:
                raise RuntimeError('recruitment binding changed during cleanup: ' + name)
        for cls, name, original, replacement in self.bindings:
            setattr(cls, name, original)
        self.active = False
        self.emit('p04d_recruit_policy', phase='restore', exact_original_bindings_restored=True)


def init(record):
    global _guard
    if _guard is not None:
        raise RuntimeError('recruitment policy initialized twice')
    import crew_capabilities
    from gui.Scaleform.daapi.business_layer import BusinessHandler
    from gui.Scaleform.daapi.view.lobby.recruitWindow.RecruitWindow import RecruitWindow
    from gui import SystemMessages
    capability = crew_capabilities._guard
    if capability is None or not capability.active:
        raise RuntimeError('active crew capability policy required')
    if any((row[0] is BusinessHandler and row[1] == '_BusinessHandler__showRecruitWindow')
           or (row[0] is RecruitWindow and row[1] == 'buyTankman') for row in capability.bindings):
        raise RuntimeError('crew policy must explicitly allow only open_recruit/recruit first')
    if set(getattr(capability, 'allowed_actions', ())) != set(('open_recruit', 'recruit')):
        raise RuntimeError('exact recruitment capability opt-in required')
    candidate = _RecruitGuard(BusinessHandler, RecruitWindow, SystemMessages, record)
    candidate.install()
    _guard = candidate


def fini():
    """After original view/listener disposal, before crew_capabilities.fini()."""
    global _guard
    if _guard is not None:
        _guard.restore()
        _guard = None


def native_snapshot():
    """Read original inventory objects, including native descriptor parse/repack."""
    import BigWorld
    from gui.shared import g_itemsCache
    from gui.shared.gui_items import ItemsCollection
    from CurrentVehicle import g_currentVehicle
    from ConnectionManager import connectionManager
    if BigWorld.player() is None or not connectionManager.isConnected() or not g_itemsCache.isSynced():
        raise RuntimeError('native snapshot requires connected synced Account')
    items = g_itemsCache.items
    tankmen = items.getTankmen()
    # Original ItemsRequester.getTankmen line430 creates ItemsCollection,
    # a dict subclass (gui_items/__init__.pyc class73), not a plain dict.
    if not isinstance(tankmen, ItemsCollection) or not 1 <= len(tankmen) <= 16:
        raise ValueError('bounded native tankman inventory required')
    rows = []
    for identity, item in sorted(tankmen.items()):
        _integer(identity, 1, 2147483647)
        compact, desc = item.strCD, item.descriptor
        if not isinstance(compact, bytes) or len(compact) != 25 or desc.makeCompactDescr() != compact:
            raise ValueError('actual native tankman descriptor failed size/parse/repack check')
        if item.invID != identity:
            raise ValueError('native tankman inventory key disagrees with item')
        row = dict(inventory_id=identity, vehicle_inventory_id=_integer(item.vehicleInvID, -1, 2147483647),
                   slot=_integer(item.vehicleSlotIdx, -1, 7), sha256=hashlib.sha256(compact).hexdigest(),
                   nation_id=_integer(desc.nationID, 0, 15), vehicle_type_id=_integer(desc.vehicleTypeID, 1, 255),
                   role=desc.role, role_level=_integer(desc.roleLevel, 0, 100),
                   no_skills=not desc.skills, free_xp=_integer(desc.freeXP, 0, 2147483647))
        if row['role'] not in ('commander', 'driver'):
            raise ValueError('unsupported native recruitment scenario role')
        rows.append(row)
    vehicle = items.getVehicle(1)
    if vehicle is None or vehicle.intCD != 3329:
        raise ValueError('actual MS-1 inventory vehicle required')
    crew = sorted(vehicle.crew, key=lambda pair: pair[0])
    if len(crew) != 2 or [pair[0] for pair in crew] != [0, 1]:
        raise ValueError('actual MS-1 crew shape changed')
    return dict(database_id=_integer(BigWorld.player().databaseID, 1, 2147483647),
                selected_inventory_id=_integer(g_currentVehicle.invID, -1, 2147483647),
                free_quota=_integer(items.stats.freeTankmenLeft, 0, 1),
                credits=_integer(items.stats.credits, 0, 9223372036854775807),
                gold=_integer(items.stats.gold, 0, 9223372036854775807),
                ms1_crew=[None if item is None else _integer(item.invID, 1, 2147483647) for slot, item in crew],
                tankmen=rows)


def native_window_evidence(window):
    """Read public PyGFx fields; cached properties are not pixel evidence."""
    flash = window.flashObject
    if flash is None:
        raise RuntimeError('native recruitment window is not Flash-bound')
    buttons = []
    for name in ('btnAcademy', 'btnScool'):
        button = getattr(flash, name)
        if button.visible is not False or button.enabled is not False or button.type != 'free':
            raise RuntimeError('paid recruitment control is not hidden and disabled')
        buttons.append(dict(name=name, visible=button.visible, enabled=button.enabled, type=button.type))
    free = flash.btnCourses
    if (free.visible is not True or free.enabled is not True or free.type != 'free'
            or free.typeSwitcher.visible is not False or free.typeLabel.text != LABEL
            or flash.btnRecruit.enabled is not True):
        raise RuntimeError('native free recruitment control policy readback differs')
    return dict(paid_buttons=buttons, free_label=free.typeLabel.text, original_window_title_preserved=True,
                policy_level=100, policy_tariff=0, policy_quota=1,
                historical_paid_tariffs='UNKNOWN', historical_tier_levels='UNKNOWN',
                observation='PyGFx public properties; freshness may be cached', pixels='NOT_RUN')


def checked_expected(value):
    """Bound the public post-hire snapshot before arming a fresh-login check."""
    fields = set(('database_id', 'selected_inventory_id', 'free_quota', 'credits', 'gold', 'ms1_crew', 'tankmen'))
    row_fields = set(('inventory_id', 'vehicle_inventory_id', 'slot', 'sha256', 'nation_id',
                      'vehicle_type_id', 'role', 'role_level', 'no_skills', 'free_xp'))
    if type(value) is not dict or set(value) != fields:
        raise ValueError('exact public post-recruit snapshot required')
    for name, upper in (('database_id', 2147483647), ('credits', 9223372036854775807), ('gold', 9223372036854775807)):
        _integer(value[name], 1 if name == 'database_id' else 0, upper)
    _integer(value['selected_inventory_id'], 1, 1)
    _integer(value['free_quota'], 0, 0)
    if (value['selected_inventory_id'] != 1 or value['free_quota'] != 0
            or type(value['ms1_crew']) is not list or len(value['ms1_crew']) != 2
            or type(value['tankmen']) is not list or len(value['tankmen']) != 3):
        raise ValueError('one completed MS-1 hire and exhausted quota required')
    for identity in value['ms1_crew']:
        _integer(identity, 1, 2147483647)
    rows = {}
    for row in value['tankmen']:
        if type(row) is not dict or set(row) != row_fields:
            raise ValueError('exact native tankman snapshot row required')
        identity = _integer(row['inventory_id'], 1, 2147483647)
        if identity in rows:
            raise ValueError('duplicate expected native tankman identity')
        _integer(row['vehicle_inventory_id'], -1, 2147483647)
        _integer(row['slot'], -1, 1)
        for name, exact in (('nation_id', 0), ('vehicle_type_id', 13), ('role_level', 100), ('free_xp', 0)):
            _integer(row[name], exact, exact)
        if (row['nation_id'] != 0 or row['vehicle_type_id'] != 13 or row['role_level'] != 100
                or row['no_skills'] is not True or row['free_xp'] != 0
                or row['role'] not in ('commander', 'driver') or not isinstance(row['sha256'], string_types)
                or re.match(r'\A[0-9a-f]{64}\Z', row['sha256']) is None):
            raise ValueError('expected native tankman policy differs')
        rows[identity] = row
    if len(set(value['ms1_crew'])) != 2 or not set(value['ms1_crew']).issubset(rows):
        raise ValueError('expected MS-1 assignments do not refer to distinct owned tankmen')
    for identity, row in rows.items():
        if identity in value['ms1_crew']:
            slot = value['ms1_crew'].index(identity)
            if row['vehicle_inventory_id'] != 1 or row['slot'] != slot or row['role'] != ('commander', 'driver')[slot]:
                raise ValueError('expected native assignment differs from crew seat')
        elif row['vehicle_inventory_id'] != -1 or row['slot'] != -1:
            raise ValueError('replaced tankman must be in barracks')
    if rows[value['ms1_crew'][1]]['sha256'] != DRIVER_SHA256:
        raise ValueError('recruited driver differs from pinned compact descriptor')
    return dict(value, ms1_crew=list(value['ms1_crew']), tankmen=[dict(row) for row in value['tankmen']])


class _Screenshots(object):
    """Only the original engine writes screenshots to the prepared owned trace."""
    def __init__(self, settings):
        from project_preferences import owned
        import Settings
        requested = settings['screenshot_dir']
        if not os.path.isabs(requested) or not os.path.isdir(requested):
            raise ValueError('prepared absolute screenshot directory required')
        self.directory = owned(requested, settings['local_root'])
        if self.directory != owned(os.path.join(settings['trace_dir'], 'screenshots'), settings['local_root']):
            raise ValueError('recruitment screenshots must belong to the prepared trace')
        configured = Settings.g_instance.engineConfig.readString('screenShot/path')
        if not os.path.isabs(configured) or owned(configured, settings['local_root']) != self.directory:
            raise ValueError('original engine screenshot destination differs from owned trace')
        self.requested = set()

    def _entries(self):
        names = os.listdir(self.directory)
        if len(names) > 128:
            raise ValueError('screenshot directory entry bound exceeded')
        return names

    def capture(self, name, record):
        if name not in ('p04d_recruit_window', 'p04d_recruit_after', 'p04d_recruit_relogin'):
            raise ValueError('unsupported recruitment screenshot name')
        if name not in self.requested:
            if any(entry.startswith(name + '_') for entry in self._entries()):
                raise ValueError('recruitment screenshot basename is occupied')
            import BigWorld
            self.requested.add(name)
            BigWorld.screenShot('png', name)
            record('p04d_recruit_screenshot_requested', version=VERSION, policy=POLICY,
                   basename=name, writer='BigWorld.screenShot', directory=self.directory)
        names = [entry for entry in self._entries()
                 if re.match(r'\A' + re.escape(name) + r'_[0-9]{3,10}\.png\Z', entry)]
        if not names:
            return None
        if len(names) != 1:
            raise ValueError('ambiguous native recruitment screenshot')
        from project_preferences import owned
        from ms1_crew_scenario import png_evidence
        path = owned(os.path.join(self.directory, names[0]), self.directory)
        if not os.path.isfile(path) or os.path.islink(path):
            raise ValueError('native recruitment screenshot must be an owned regular file')
        return png_evidence(path, name)


class NativeScenario(object):
    """Explicit diagnostic API: advance from caller, never self-launch/relogin.

    recruit: original Crew open callback, then guarded original buy callback
    once, then actual inventory observation. relogin: read only, compare the
    exact prior snapshot supplied by the caller after a genuine fresh login.
    This is native callback acceptance; physical clicks/pixels are separate.
    """
    def __init__(self, record, mode='recruit', expected=None, settings=None, clock=None):
        if not callable(record) or mode not in ('recruit', 'relogin'):
            raise ValueError('explicit bounded recruitment diagnostic mode required')
        if (mode == 'relogin') != (expected is not None):
            raise ValueError('relogin requires prior successful snapshot only')
        self.record, self.mode = record, mode
        self.expected = checked_expected(expected) if mode == 'relogin' else None
        self.phase, self.advances, self.before, self.after = 'wait_hangar', 0, None, None
        self.clock = clock if clock is not None else time.monotonic if hasattr(time, 'monotonic') else time.clock
        self.started = self.clock()
        if type(self.started) not in (int, float) or math.isnan(self.started) or math.isinf(self.started):
            raise ValueError('finite monotonic recruitment clock required')
        self.last_time, self.ready_since = self.started, None
        self.screenshots = None if settings is None else _Screenshots(settings)
        self.captures = []

    def advance(self, ready_hangar):
        if type(ready_hangar) is not bool:
            raise ValueError('explicit native Hangar readiness required')
        if self.phase == 'complete':
            return True
        if self.phase == 'error':
            raise RuntimeError('failed native recruitment scenario cannot continue')
        now = self.clock()
        if (type(now) not in (int, float) or math.isnan(now) or math.isinf(now)
                or now < self.last_time or now - self.started > 180):
            self.phase = 'error'
            raise RuntimeError('finite monotonic recruitment scenario deadline180s exceeded')
        self.last_time = now
        if (self.phase == 'window_ready' and self.screenshots is not None
                and now - self.ready_since > 20):
            self.phase = 'error'
            raise RuntimeError('original recruitment window screenshot deadline20s exceeded')
        self.advances += 1
        if self.advances > 600:
            self.phase = 'error'
            raise RuntimeError('bounded recruitment scenario observation budget exhausted')
        try:
            return self._advance(ready_hangar)
        except Exception:
            self.phase = 'error'
            raise

    def _advance(self, ready_hangar):
        if self.phase in ('wait_hangar', 'wait_ms1') and not ready_hangar:
            return False
        from gui.WindowsManager import g_windowsManager
        from gui.Scaleform.framework import ViewTypes
        from gui.Scaleform.Waiting import Waiting
        from gui.Scaleform.daapi.settings.views import VIEW_ALIAS
        from gui.Scaleform.framework.managers.containers import POP_UP_CRITERIA
        manager = g_windowsManager.window.containerManager
        page = manager.getContainer(ViewTypes.LOBBY_SUB).getView()
        if type(page).__name__ != 'Hangar' or page.flashObject is None:
            raise RuntimeError('original Hangar required for recruitment scenario')
        if Waiting.isVisible():
            return False
        if self.phase == 'wait_hangar':
            self.phase = 'wait_ms1'
            # Native GUI selection, not an inventory/assignment mutation.
            page.tankCarousel.vehicleChange(1)
            self.record('p04d_recruit_select_ms1', version=VERSION, policy=POLICY,
                        original_callback='TankCarousel.vehicleChange', native_vehicle_id=1)
            return False
        if self.phase == 'wait_ms1':
            from CurrentVehicle import g_currentVehicle
            if g_currentVehicle.invID != 1:
                return False
            if self.mode == 'relogin':
                actual = native_snapshot()
                if actual != self.expected or actual['free_quota'] != 0:
                    raise RuntimeError('fresh-login native inventory differs from post-recruit snapshot')
                self.after = actual
                return self._finish_or_capture()
            if _guard is None or not _guard.active or _guard.submitted:
                raise RuntimeError('fresh active recruitment UI policy required')
            before = native_snapshot()
            if before['selected_inventory_id'] != 1 or before['free_quota'] != 1:
                raise RuntimeError('select MS-1 with one quota before recruitment diagnostic')
            self.before = before
            self.record('p04d_recruit_before', version=VERSION, policy=POLICY, snapshot=before)
            self.phase = 'wait_window'
            page.crewPanel.onShowRecruitWindowClick(dict(TARGET_DATA), False)
            return False
        if self.phase in ('wait_window', 'window_ready'):
            window = manager.getContainer(ViewTypes.WINDOW).getView(
                criteria={POP_UP_CRITERIA.VIEW_ALIAS: VIEW_ALIAS.RECRUIT_WINDOW})
            if window is None or window.flashObject is None:
                return False
            if type(window) is not _guard.window_class or not _guard._window_ok(window):
                raise RuntimeError('unexpected original RecruitWindow instance')
            observation = native_window_evidence(window)
            if self.phase == 'wait_window':
                self.record('p04d_recruit_window_observed', version=VERSION, policy=POLICY,
                            observation=observation)
                # One full caller observation interval for an engine-written
                # screenshot of the original window before any submission.
                self.phase = 'window_ready'
                self.ready_since = self.last_time
                return False
            if self.screenshots is not None:
                elapsed = self.last_time - self.ready_since
                if elapsed > 20:
                    raise RuntimeError('original recruitment window screenshot deadline20s exceeded')
                if elapsed < 2:
                    return False
                capture = self.screenshots.capture('p04d_recruit_window', self.record)
                if capture is None:
                    return False
                self.captures.append(capture)
            self.phase = 'wait_inventory'
            window.buyTankman(0, 13, 'driver', 0, 1)
            return False
        if self.phase == 'wait_inventory':
            actual = native_snapshot()
            if actual == self.before:
                return False
            verify_recruit_transition(self.before, actual)
            self.after = actual
            return self._finish_or_capture()
        if self.phase == 'after_ready':
            if not ready_hangar or self.last_time - self.ready_since < 2:
                return False
            window = manager.getContainer(ViewTypes.WINDOW).getView(
                criteria={POP_UP_CRITERIA.VIEW_ALIAS: VIEW_ALIAS.RECRUIT_WINDOW})
            if window is not None:
                return False
            if native_snapshot() != self.after:
                raise RuntimeError('native crew changed while awaiting screenshot evidence')
            name = 'p04d_recruit_relogin' if self.mode == 'relogin' else 'p04d_recruit_after'
            capture = self.screenshots.capture(name, self.record)
            if capture is None:
                return False
            self.captures.append(capture)
            return self._finish()
        raise RuntimeError('unsupported native recruitment scenario phase')

    def _finish_or_capture(self):
        if self.screenshots is None:
            return self._finish()
        self.phase, self.ready_since = 'after_ready', self.last_time
        return False

    def _finish(self):
        self.phase = 'complete'
        if self.mode == 'relogin':
            self.record('p04d_recruit_relogin', version=VERSION, policy=POLICY,
                        snapshot=self.after, action='read_only', exact_snapshot_match=True,
                        screenshots=self.captures, visual_acceptance='NOT_RUN')
        else:
            self.record('p04d_recruit_after', version=VERSION, policy=POLICY, snapshot=self.after,
                        new_inventory_id=self.after['ms1_crew'][1], action='native_inventory_readback',
                        screenshots=self.captures,
                        visual_acceptance='NOT_RUN', physical_click_acceptance='NOT_RUN')
        return True


def verify_recruit_transition(before, after):
    """One added identity, same old descriptors, one seat replacement, quota -1."""
    for key in ('database_id', 'selected_inventory_id', 'credits', 'gold'):
        if after[key] != before[key]:
            raise RuntimeError('unrelated native account field changed during recruitment')
    old = dict((row['inventory_id'], row) for row in before['tankmen'])
    new = dict((row['inventory_id'], row) for row in after['tankmen'])
    added = set(new) - set(old)
    if (len(added) != 1 or set(old) - set(new) or before['free_quota'] != 1 or after['free_quota'] != 0
            or after['ms1_crew'][0] != before['ms1_crew'][0] or after['ms1_crew'][1] not in added):
        raise RuntimeError('native recruitment did not add exactly one driver and consume one quota')
    identity = after['ms1_crew'][1]
    hired = new[identity]
    if (hired['sha256'] != DRIVER_SHA256 or hired['vehicle_inventory_id'] != 1 or hired['slot'] != 1
            or hired['nation_id'] != 0 or hired['vehicle_type_id'] != 13 or hired['role'] != 'driver'
            or hired['role_level'] != 100 or hired['no_skills'] is not True or hired['free_xp'] != 0):
        raise RuntimeError('new native driver differs from measured project descriptor policy')
    for old_id, row in old.items():
        expected = dict(row)
        if old_id == before['ms1_crew'][1]:
            expected.update(vehicle_inventory_id=-1, slot=-1)
        if new[old_id] != expected:
            raise RuntimeError('existing crew changed outside the replaced driver assignment')
    return identity
