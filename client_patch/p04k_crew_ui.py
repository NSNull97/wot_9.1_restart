# -*- coding: utf-8 -*-
"""Original Barracks lists/selectors and server-authoritative free50 CMD303.

The existing dismissal/transfer/learning guards remain installed. This adapter
admits the source-defined unseated recruitment context and masks only the
unsupported berth-purchase renderer. No native inventory or reply is written.
"""
import binascii
import copy
import hashlib
import math
import os
import re
import time
import crew_vehicles
import p04d_crew_ui as recruitment
import p04f_crew_ui as transfer
import p04g_crew_ui as cross
import p04h_crew_ui as roster
import p04i_crew_ui as progression
import p04j_crew_ui as dismissal

VERSION = 1
POLICY = 'test_lab.ms1_is7.barracks.free50.sparse16.v1'
ROLE_LEVEL = 50
SHOP_REVISION = 3
# The original P09E shop cache is revision 5 on this profile.  The server
# normalizes that profile13 value to its internal P04K revision (3) at the
# account-service boundary; the untouched native callback still sends 5.
NATIVE_CACHE_REVISION = 5
SHOP_SHA256 = 'b55573c5b14fbbc034fbc2091d9e381645926c67e561ab46917ecd3d6965129a'
BERTH_NOTICE = u'Покупка мест недоступна'
NOTICE = u'Найм в казарму: 50%, бесплатно, в пределах серверной квоты. Покупка мест и платное обучение недоступны.'
VEHICLES = dismissal.VEHICLES
ROLES = {'commander': 1, 'driver': 3, 'gunner': 4, 'loader': 5}
STEPS = (('hire_is7_gunner_12', 2, 'gunner', 12), ('hire_ms1_commander_13', 1, 'commander', 13))
integer = roster.integer
checked_expected = dismissal.checked_expected
native_snapshot = dismissal.native_snapshot
_guard = _record = _scenario = None
_ABSENT = object()

# CREW-ANY lifetime is deliberately a separate controller from the accepted
# MS-1/IS-7 two-hire evidence scenario below.  The old scenario keeps its
# frozen expectations; this controller is the only path allowed to exercise
# the v2 allocator's 18..192 range.
LIFETIME_FIRST = 18
LIFETIME_LAST = 192
LIFETIME_REJECT = 193
LIFETIME_SELECTOR_BUDGET = 8
LIFETIME_SELECTOR_DEADLINE = 25
LIFETIME_DEADLINE = 3600


def max_tankmen():
    return crew_vehicles.max_tankmen(16)


def _shop_revision(value):
    """Read the native cache revision without rejecting Python-2 numeric wrappers.

    The #717 client exposes this value as an integral ``float`` on the
    CREW-ANY account after the catalog overlay is enabled.  Preserve the
    strict value/range check while normalizing only that native representation;
    no revision is invented or written back to the client cache.
    """
    if type(value) is float and value == int(value):
        value = int(value)
    if value not in (SHOP_REVISION, NATIVE_CACHE_REVISION):
        raise ValueError('unsupported native shop cache revision')
    return integer(value, SHOP_REVISION, NATIVE_CACHE_REVISION)


def checked_hires(rows):
    if type(rows) is not list or len(rows) != 2:
        raise ValueError('two exact unassigned native hire rows required')
    for row, step in zip(rows, STEPS):
        name, vehicle, role, identity = step
        if type(row) is not dict or set(row) != dismissal.ROW_FIELDS:
            raise ValueError('exact sparse hire row fields required')
        expected = dict(inventory_id=identity, vehicle_inventory_id=-1, slot=-1,
                        nation_id=0, vehicle_type_id=VEHICLES[vehicle][1], role=role,
                        role_level=50, skills=[], last_skill_level=0, free_xp=0,
                        dossier_bytes=6, dossier_sha256=dismissal.DOSSIER_SHA256)
        if any((type(row[key]) is not type(value) if not isinstance(value, recruitment.string_types)
                else not isinstance(row[key], recruitment.string_types)) or row[key] != value
               for key, value in expected.items()):
            raise ValueError('source-bound unassigned free50 hire differs')
        if not isinstance(row['sha256'], recruitment.string_types) or re.match(r'\A[0-9a-f]{64}\Z', row['sha256']) is None:
            raise ValueError('precomputed server descriptor SHA required')
    return copy.deepcopy(rows)


def projected_hire(snapshot, row):
    """Evidence expectation only; this never touches a GUI object/cache."""
    result = checked_expected(snapshot, ROLE_LEVEL)
    if (result['free_quota'] <= 0 or row['inventory_id'] != 17 - result['free_quota']
            or row['inventory_id'] in dismissal.member_map(result)
            or row['vehicle_inventory_id'] != -1 or row['slot'] != -1):
        raise ValueError('lifetime allocator/quota or unassigned hire differs')
    result['tankmen'].append(copy.deepcopy(row))
    result['free_quota'] -= 1
    return checked_expected(result, ROLE_LEVEL)


def native_shop():
    import BigWorld
    from gui.shared import g_itemsCache
    shop = BigWorld.player().shop
    revision = _shop_revision(shop._Shop__getCacheRevision())
    stats = g_itemsCache.items.stats
    berths = integer(stats.tankmenBerthsCount, 16, 16)
    members = g_itemsCache.items.getTankmen().values()
    count = sum(not item.isInTank for item in members)
    integer(count, 0, 16)
    unlocks = stats.unlocks
    if crew_vehicles.enabled():
        # The original selector lists unlocked types; serve the catalog ones.
        unlocked = sorted(identity for identity in crew_vehicles.mounts(None) if identity in unlocks)
        return dict(revision=revision, berths=berths, unassigned=count,
                    free_berths=berths - count, unlocked_vehicle_types=unlocked)
    if not all(VEHICLES[vehicle][0] in unlocks for vehicle in (1, 2)):
        raise RuntimeError('original selector requires both source vehicle unlocks')
    return dict(revision=revision, berths=berths, unassigned=count,
                free_berths=berths - count, unlocked_vehicle_types=[3329, 7169])


def _unseated(window):
    return (type(window._currentVehicleInvId) in recruitment.integer_types
            and window._currentVehicleInvId == -1 and window._menuEnabled is True
            and window._initData is None)


class _RecruitGuard(dismissal._RecruitGuard):
    def __init__(self, *args, **kwargs):
        super(_RecruitGuard, self).__init__(*args, **kwargs)
        self.selectors = []
        for name in ('updateNationDropdown', 'updateVehicleClassDropdown', 'updateVehicleTypeDropdown', 'updateRoleDropdown'):
            original = self.window_class.__dict__[name]
            self.bindings.append((self.window_class, name, original, self._selector(original, name)))

    def _selector(self, original, name):
        guard = self
        def selector(window, *args):
            result = original(window, *args)
            if _unseated(window):
                if len(guard.selectors) >= 128:
                    raise RuntimeError('native selector observation budget exhausted')
                values = []
                for value in args:
                    if (isinstance(value, recruitment.string_types) and len(value) <= 64
                            or type(value) in recruitment.integer_types + (float,)):
                        values.append(value)
                    else:
                        raise ValueError('bounded original selector arguments required')
                event = dict(owner_id=id(window), method=name, arguments=values, original_callback_returned=True)
                guard.selectors.append(event)
                guard.record('p04k_native_selector', **event)
                guard._mask(window, guard._state())
            return result
        return selector

    def _open(self, original):
        seated = super(_RecruitGuard, self)._open(original)
        guard = self
        def opened(owner, event):
            ctx = event.ctx
            if type(ctx) is dict and ctx == dict(data=None, menuEnabled=True):
                state = guard._state()
                if _guard is None or _guard.current is None or not _guard.current._isDAAPIInited():
                    return guard._deny('barracks_window_owner_unavailable')
                guard.record('p04k_barracks_open', owner_id=id(_guard.current),
                             context=dict(data=None, menuEnabled=True), free_quota=state['free_quota'],
                             original_callback_called=True)
                return original(owner, event)
            return seated(owner, event)
        return opened

    def _window_ok(self, window):
        return _unseated(window) or super(_RecruitGuard, self)._window_ok(window)

    def _mask(self, window, state):
        if not _unseated(window):
            return super(_RecruitGuard, self)._mask(window, state)
        # Only the tariff controls: original selector handlers own all four
        # dropdown enabled states and their source-produced data providers.
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
        free.enabled = state['free_quota'] > 0 and len(state['tankmen']) < max_tankmen() and not self.submitted
        free.typeLabel.text = roster.LABEL % state['free_quota']
        flash.btnRecruit.enabled = free.enabled

    def _initial(self, original):
        seated = super(_RecruitGuard, self)._initial(original)
        guard = self
        def initial(window):
            if not _unseated(window):
                return seated(window)
            state = guard._state()
            if window in guard.windows or len(guard.windows) >= 32:
                raise RuntimeError('bounded fresh original recruitment window required')
            guard.windows.append(window)
            guard.window, guard.submitted = window, False
            # Same original VO as accepted H free-only adapter; no paid prices.
            guard._mask(window, state)
            window.flashObject.as_initData(dict(credits=state['credits'], gold=state['gold'],
                data=None, menuEnabled=True, schoolUpgradeActionPriceData=None,
                academyUpgradeActionPriceData=None))
            window.flashObject.validateNow()
            guard._mask(window, state)
            guard.record('p04k_barracks_window_ready', owner_id=id(window), menu_enabled=True,
                         current_vehicle_id=-1, role_level=50, free_quota=state['free_quota'],
                         paid_controls_hidden=True, original_selector_callbacks_preserved=True)
        return initial

    def _buy(self, original):
        seated = super(_RecruitGuard, self)._buy(original)
        guard = self
        def buy(window, nationID, vehTypeID, role, studyType, slot):
            if not _unseated(window):
                return seated(window, nationID, vehTypeID, role, studyType, slot)
            state = guard._state()
            shop = native_shop()
            pending = getattr(_scenario, 'pending', None)
            if crew_vehicles.enabled():
                # Unlocked catalog types the original selector offers, keyed by compact ID.
                served = dict((cd, (cd, cd >> 8, None, tuple(crew_vehicles.kind_by_type(cd >> 8)['primary_roles'])))
                              for cd in shop['unlocked_vehicle_types'])
            else:
                served = VEHICLES
            vehicle = next((identity for identity in sorted(served)
                            if recruitment._number_equals(vehTypeID, served[identity][1])), None)
            lifetime_reject = (_scenario is not None and
                               getattr(_scenario, 'mode', None) == 'lifetime' and
                               getattr(_scenario, 'phase', None) in ('reject_wait_result', 'wait_result') and
                               type(pending) is dict and pending.get('expect') == -10 and
                               state['free_quota'] == 0)
            if (window is not guard.window or vehicle is None or role not in served[vehicle][3]
                    or not recruitment._number_equals(nationID, 0)
                    or not recruitment._number_equals(studyType, 0)
                    or not (slot is None or recruitment._number_equals(slot, -1))
                    or (state['free_quota'] <= 0 and not lifetime_reject)
                    or shop['free_berths'] <= 0 or guard.submitted):
                return guard._deny('unsupported_barracks_target_tariff_capacity_or_submission')
            guard.submitted = True
            guard._mask(window, state)
            guard.record('p04k_barracks_submit', owner_id=id(window), native_cmd=303,
                         vehicle_type=served[vehicle][0], role=role, tariff=0, role_level=50,
                         shop=shop, original_callback_called=True, original_processor='TankmanRecruit')
            return original(window, nationID, vehTypeID, role, studyType, slot)
        return buy


def _field(value, name, default=None):
    return value.get(name, default) if type(value) is dict else getattr(value, name, default)


def _renderer_row(data):
    if data is None:
        return None
    buy, empty, tankman = _field(data, 'buy'), _field(data, 'empty'), _field(data, 'tankmanID')
    if sum((buy is True, empty is True, tankman is not None)) != 1:
        return None
    if buy is True:
        return ['buy', None]
    if empty is True:
        return ['empty', None]
    return ['tankman', dismissal.callback_integer(tankman, 1, max_tankmen())]


def _logical_renderers(tile, model):
    # TileList retains a physical pool beyond dataProvider.length. Its unused
    # renderers receive null, but BarracksItemRenderer.setData returns before
    # clearing their previous data. Address only original logical rows.
    expected = [['tankman', identity] for identity in model['row_ids']]
    if model['unassigned'] < model['capacity']:
        expected.append(['empty', None])
    expected.append(['buy', None])
    provider = tile.dataProvider
    actual = None
    if provider is not None:
        length = len(provider) if type(provider) is list else dismissal.callback_integer(provider.length, 0, max_tankmen() + 2)
        integer(length, 0, max_tankmen() + 2)
        actual = [_renderer_row(provider[index]) for index in range(length)]
    # Native04 observed a stale reflected provider after inventory update while
    # original getData() returned every current row. Preserve that raw snapshot
    # as diagnostic data; never substitute or normalize it into current rows.
    scroll = dismissal.callback_integer(tile.scrollPosition, 0, max_tankmen() + 1)
    result, pending, rendered = [], [], []
    for index, row in enumerate(expected):
        # Original TileList.updateSelectedIndex uses this same public pair.
        renderer = tile.getRendererAt(index, scroll)
        if renderer is None:
            continue
        rendered_index = dismissal.callback_integer(renderer.index, 0, max_tankmen() + 1)
        data = renderer.getData()
        rendered_row = _renderer_row(data)
        observation = dict(index=index, rendered_index=rendered_index, method_row=rendered_row,
                           raw_property_row=_renderer_row(renderer.data))
        rendered.append(observation)
        if rendered_index != index or rendered_row != row:
            pending.append(observation)
            # The original TileList can expose the source-created buy card at
            # a retained-pool tail slot after a 17-member refresh. Keep that
            # card usable when its native getData() still proves it is the
            # buy row. Only the two tail slots are eligible, so an in-range
            # stale buy renderer cannot mask a tankman row.
            buy_tail_start = max(len(expected) - 2, 0)
            if (rendered_row == ['buy', None]
                    and buy_tail_start <= rendered_index < len(expected)):
                result.append((index, renderer, data))
            continue
        result.append((index, renderer, data))
    return result, dict(ready=not pending, logical_count=len(expected), scroll_position=scroll,
                        expected_rows=expected, rendered_rows=rendered, pending_renderers=pending,
                        raw_provider_rows=actual, provider_readback='OBSERVATION_ONLY',
                        provider_matches_logical_rows=actual == expected)


class _BarracksGuard(object):
    """Capture unchanged original list VO; mask only its unsupported buy tile."""
    def __init__(self, cls, record):
        self.cls, self.record = cls, record
        self.active, self.current, self.callback, self.error = False, None, None, None
        self.model, self.paint_count, self.previous = None, 0, []
        self.bindings = []
        for name, factory in (('as_setTankmenS', self._data), ('_dispose', self._dispose)):
            original = next(base.__dict__[name] for base in cls.__mro__ if name in base.__dict__)
            self.bindings.append((name, cls.__dict__.get(name, _ABSENT), original, factory(original)))

    def _data(self, original):
        guard = self
        def data(page, total, capacity, unassigned, price, action, pack, rows):
            # capacity/unassigned are the original 16 berths; total is the whole roster.
            integer(total, 0, max_tankmen()); integer(capacity, 16, 16); integer(unassigned, 0, 16)
            if type(rows) is not list or len(rows) > total or any(type(row) is not dict for row in rows):
                raise ValueError('bounded actual original Barracks rows required')
            ids = [dismissal.callback_integer(row.get('tankmanID'), 1, max_tankmen()) for row in rows]
            if len(set(ids)) != len(ids):
                raise ValueError('duplicate native Barracks renderer identity')
            # Original TileList replaces/disposes renderers when its data changes.
            # Restore our display-only values while the old objects are alive.
            guard._restore_paint()
            result = original(page, total, capacity, unassigned, price, action, pack, rows)
            guard.current = page
            guard.model = dict(total=total, capacity=capacity, unassigned=unassigned,
                               row_ids=ids, filter=copy.deepcopy(page.filter), original_rows_unchanged=True)
            guard.record('p04k_barracks_list', owner_id=id(page), **guard.model)
            return result
        return data

    def _dispose(self, original):
        guard = self
        def dispose(page):
            if guard.current is page:
                guard._restore_paint()
                guard.current, guard.model = None, None
            return original(page)
        return dispose

    def _restore_paint(self):
        for renderer, enabled, label, visible in self.previous:
            # Original BarracksItemRenderer.onDispose11456 clears _data,
            # countField and descrField. A retained PyGFx proxy then names a
            # disposed object, not a live widget that can be restored.
            if renderer.data is None and renderer.countField is None and renderer.descrField is None:
                self.record('p04k_barracks_renderer_released', reason='original_disposed_fields',
                            original_data_null=True, original_count_null=True, original_description_null=True,
                            restoration_required=False)
                continue
            renderer.enabled = enabled
            renderer.descrField.text = label
            for name, value in zip(('price', 'actionPrice', 'countField'), visible):
                getattr(renderer, name).visible = value
        self.previous = []

    def paint(self):
        if self.current is None or self.current.flashObject is None or self.model is None:
            return 0
        self._restore_paint()
        tile = self.current.flashObject.form.tankmenTileList
        matched = 0
        renderers, layout = _logical_renderers(tile, self.model)
        if not layout['ready']:
            self.record('p04k_barracks_renderers_pending', **layout)
        for index, renderer, data in renderers:
            if _field(data, 'buy') is not True:
                continue
            renderer.validateNow()
            fields = [getattr(renderer, name) for name in ('descrField', 'price', 'actionPrice', 'countField')]
            if any(field is None for field in fields):
                # A source-created renderer can be present before its children
                # are ready. It does not count as a masked/accepted purchase row.
                self.record('p04k_barracks_renderer_pending', renderer_slot=index,
                            missing_fields=[name for name, field in zip(('descrField', 'price', 'actionPrice', 'countField'), fields) if field is None])
                continue
            self.previous.append((renderer, renderer.enabled, renderer.descrField.text,
                                  [getattr(renderer, name).visible for name in ('price', 'actionPrice', 'countField')]))
            renderer.enabled = False
            renderer.descrField.text = BERTH_NOTICE
            for name in ('price', 'actionPrice', 'countField'):
                getattr(renderer, name).visible = False
            matched += 1
        if matched > 1:
            raise RuntimeError('more than one original berth purchase tile')
        self.paint_count += 1
        return matched

    def _tick(self):
        import BigWorld
        self.callback = None
        if not self.active:
            return
        try:
            self.paint()
        except Exception as error:
            self.error = str(error)
            self.record('p04k_barracks_mask_error', error=self.error, acceptance='FAIL')
            raise
        self.callback = BigWorld.callback(0.25, self._tick)

    def install(self):
        import BigWorld
        if self.active:
            raise RuntimeError('Barracks guard already active')
        for name, own, original, replacement in self.bindings:
            if self.cls.__dict__.get(name, _ABSENT) is not own:
                raise RuntimeError('Barracks original binding changed')
            setattr(self.cls, name, replacement)
        self.active = True
        self.callback = BigWorld.callback(0.25, self._tick)

    def restore(self):
        import BigWorld
        if self.callback is not None:
            BigWorld.cancelCallback(self.callback)
            self.callback = None
        if not self.active:
            return
        self._restore_paint()
        for name, own, original, replacement in self.bindings:
            if self.cls.__dict__.get(name) is not replacement:
                raise RuntimeError('unexpected Barracks binding during restoration')
            if own is _ABSENT:
                delattr(self.cls, name)
            else:
                setattr(self.cls, name, own)
        self.active, self.current, self.model = False, None, None


def init(record):
    global _guard, _record
    import crew_capabilities
    from gui.Scaleform.daapi.view.lobby.barracks.Barracks import Barracks
    if _guard is not None or getattr(crew_capabilities._guard, 'allow_barracks', False) is not True:
        raise RuntimeError('exclusive explicit Barracks capability required')
    dismissal.init(record)
    old = dismissal._recruit_guard
    old.restore()
    candidate = _RecruitGuard(old.business_class, old.window_class, old.messages, record, old.native)
    guard = _BarracksGuard(Barracks, record)
    try:
        candidate.install()
        dismissal._recruit_guard = candidate
        guard.install()
    except Exception:
        guard.restore()
        dismissal.fini()
        raise
    _guard, _record = guard, record
    record('p04k_barracks_policy', phase='install', version=VERSION, policy=POLICY,
           original_303=True, native_cache_unchanged=True, berth_purchase=False, paid_recruitment=False)


def fini():
    global _guard, _record, _scenario
    if _guard is not None:
        _guard.restore()
    dismissal.fini()
    _guard = _record = _scenario = None


def observe_profile(frame, phase):
    if _record is None:
        return
    dismissal.observe_profile(frame, phase)
    code, values = frame.f_code, frame.f_locals
    if (phase == 'return' and code.co_filename == 'scripts/client/Account.py'
            and code.co_name == '__doCmd' and values.get('cmd') == 303):
        if (code.co_firstlineno, hashlib.sha256(code.co_code).hexdigest()) != progression.COMMAND_PIN:
            raise RuntimeError('original303 request observer source differs')
        args = values.get('args')
        if type(args) is not tuple or len(args) != 4 or any(type(v) not in recruitment.integer_types for v in args):
            raise ValueError('exact original303 Int4 arguments required')
        _record('p04k_native_barracks_request', native_cmd=303, layout=list(args),
                request_id=integer(values.get('requestID'), 1, 32767), owner_id=id(values['self']),
                source=code.co_filename, source_line=code.co_firstlineno, phase=phase)
    if (phase in ('call', 'return') and code.co_filename == 'scripts/client/account_helpers/Shop.py'
            and code.co_name == '<lambda>' and code.co_firstlineno == 800):
        if hashlib.sha256(code.co_code).hexdigest() != '295ac0b6f67a10f900820e4d0efee27c4d31937597584e2a632d608660002d3f':
            raise RuntimeError('original303 response proxy source differs')
        ext = values.get('ext')
        result = integer(values.get('resultID'), -2147483648, 0)
        if result != 0:
            _record('p04k_native_barracks_proxy', request_id=integer(values.get('requestID'), 1, 32767),
                    result=result, inventory_id=None, descriptor_hex=None, descriptor_sha256=None,
                    inventory_matches=False, phase=phase, source=code.co_filename, source_line=800)
            return
        if type(ext) is not dict or set(ext) != set(('tmanInvID', 'tmanCompDescr')):
            raise ValueError('exact original303 response extension required')
        identity, raw = integer(ext['tmanInvID'], 4, max_tankmen()), ext['tmanCompDescr']
        if not isinstance(raw, bytes) or len(raw) != 25:
            raise ValueError('source-bound25-byte hire response required')
        from gui.shared import g_itemsCache
        item = g_itemsCache.items.getTankman(identity)
        matched = item is not None and item.strCD == raw and item.descriptor.makeCompactDescr() == raw
        _record('p04k_native_barracks_proxy', request_id=integer(values.get('requestID'), 1, 32767),
                result=result, inventory_id=identity,
                descriptor_hex=binascii.hexlify(raw).decode('ascii'), descriptor_sha256=hashlib.sha256(raw).hexdigest(),
                inventory_matches=matched, phase=phase, source=code.co_filename, source_line=800)


class NativeCommandTracker(progression.NativeCommandTracker):
    def __init__(self, layout, row):
        if type(layout) is not list or len(layout) != 4 or layout[0] != SHOP_REVISION or layout[3] != 0:
            raise ValueError('exact303 shop/type/role/free layout required')
        self.command, self.layout, self.row = 303, list(layout), copy.deepcopy(row)
        self.request = self.update = self.success = None
        self.proxy = []

    def observe(self, fields):
        if fields.get('event') == 'p04k_native_barracks_request':
            fields = dict(fields, event='p04i_native_progression_request')
        if fields.get('event') == 'p04k_native_barracks_proxy':
            integer(fields.get('result'), 0, 0)
            if (self.request is None or self.update is None or self.success is not None
                    or fields.get('request_id') != self.request['request_id']
                    or fields.get('phase') != ('call' if not self.proxy else 'return') or len(self.proxy) >= 2
                    or fields.get('result') != 0 or fields.get('inventory_matches') is not True
                    or fields.get('inventory_id') != self.row['inventory_id']
                    or fields.get('descriptor_sha256') != self.row['sha256']):
                raise ValueError('original303 proxy/ext/cache ordering or identity differs')
            raw = fields.get('descriptor_hex')
            if not isinstance(raw, recruitment.string_types) or re.match(r'\A[0-9a-f]{50}\Z', raw) is None:
                raise ValueError('bounded exact native response descriptor required')
            if hashlib.sha256(binascii.unhexlify(raw)).hexdigest() != self.row['sha256']:
                raise ValueError('native ext bytes/hash differ')
            self.proxy.append(dict(fields))
        progression.NativeCommandTracker.observe(self, fields)
        if self.success is not None and len(self.proxy) != 2:
            raise ValueError('Account success without original303 proxy call/return')

    def receipt(self):
        value = progression.NativeCommandTracker.receipt(self)
        value.update(inventory_id=self.row['inventory_id'], descriptor_sha256=self.row['sha256'],
                     original_proxy_returned=len(self.proxy) == 2, inventory_before_proxy=True)
        return value


def native_event(fields):
    if _scenario is None:
        return
    try:
        event = fields.get('event')
        if event in ('p04j_native_dismissal_request', 'p04k_native_barracks_request'):
            if event == 'p04j_native_dismissal_request':
                if (_scenario.mode != 'lifetime' or _scenario.phase not in
                        ('dismissal_personal', 'dismissal_dialog', 'dismissal_wait')
                        or _scenario.pending is None):
                    raise ValueError('native CMD306 outside bounded CREW-ANY dismissal phase')
                _scenario.pending['tracker'].observe(fields)
                return
            if _scenario.pending is None or _scenario.mode not in ('recruit', 'lifetime'):
                raise ValueError('native mutation outside explicit Barracks scenario')
        if _scenario.pending is not None:
            _scenario.pending['tracker'].observe(fields)
    except (ValueError, KeyError, TypeError) as error:
        _scenario.error = str(error)


def dropdown_observation(window, name):
    if name not in ('nationDropdown', 'vehicleClassDropdown', 'vehicleTypeDropdown', 'roleDropdown'):
        raise ValueError('source-bound dropdown required')
    dropdown = getattr(window.flashObject, name)
    provider = dropdown.dataProvider
    if provider is None:
        return None
    count = len(provider) if type(provider) in (list, tuple) else dismissal.callback_integer(provider.length, 0, 256)
    integer(count, 0, 256)
    options, option_indices, source_ids = [], [], []
    for index in range(count):
        item = provider[index]
        identity = _field(item, 'id')
        if identity is None:
            # Every original provider starts with the source-defined empty row.
            pass
        elif type(identity) in recruitment.integer_types + (float,):
            identity = dismissal.callback_integer(identity, -1, 65535)
        elif not isinstance(identity, recruitment.string_types) or not 1 <= len(identity) <= 64:
            raise ValueError('bounded original dropdown id required')
        options.append(identity)
        option_indices.append(index)
        source_ids.append(identity)
    selected = dismissal.callback_integer(dropdown.selectedIndex, -1, max(count - 1, -1))
    return dict(name=name, options=options, option_indices=option_indices,
                selected_index=selected,
                selected_id=source_ids[selected] if selected >= 0 else None)


def catalog_selector_target(vehicle_type_id, role):
    """Return the source-derived selector values for one CAT-01 vehicle.

    The values are read from the generated table, never guessed from an
    inventory number.  This helper is intentionally small so the lifetime
    controller can be tested without constructing a full native Hangar.
    """
    if not crew_vehicles.enabled():
        raise RuntimeError('CREW-ANY catalog must be enabled for lifetime selectors')
    row = crew_vehicles.kind_by_type(vehicle_type_id)
    if row is None or role not in row['primary_roles']:
        raise ValueError('catalog vehicle/primary role is unsupported')
    return (('nationDropdown', 0), ('vehicleClassDropdown', row['vehicle_class']),
            ('vehicleTypeDropdown', vehicle_type_id), ('roleDropdown', role))


class BoundedCatalogSelectorController(object):
    """Drive original DropdownMenu.selectedIndex with callback readbacks.

    No private Flash handlers or synthetic callback records are used.  The
    caller invokes :meth:`advance` from its native observation tick.  A
    selection is considered complete only after the same-window original
    Python callback has been observed and the public selectedIndex reads back
    the requested source id.
    """
    def __init__(self, record, window, vehicle_type_id, role, clock=None):
        if not callable(record) or window is None:
            raise ValueError('bounded original recruitment window required')
        self.record, self.window = record, window
        self.clock = clock if clock is not None else time.monotonic if hasattr(time, 'monotonic') else time.clock
        self.targets = catalog_selector_target(vehicle_type_id, role)
        self.index, self.pending, self.waits = 0, None, 0
        self.started = self.last_time = self.clock()
        if type(self.started) not in (int, float) or math.isnan(self.started) or math.isinf(self.started):
            raise ValueError('finite selector clock required')

    def _child(self, index, vehicle_type_id):
        values = (('updateVehicleClassDropdown', [0]),
                  ('updateVehicleTypeDropdown', [0, self.targets[1][1]]),
                  ('updateRoleDropdown', [0, self.targets[1][1], vehicle_type_id]),
                  (None, None))
        return values[index]

    def _fail_deadline(self, now):
        if now - self.started > LIFETIME_SELECTOR_DEADLINE:
            raise RuntimeError('native CREW-ANY selector chain deadline exceeded')
        if self.waits > LIFETIME_SELECTOR_BUDGET:
            raise RuntimeError('native CREW-ANY selector provider readiness budget exhausted')

    def advance(self):
        now = self.clock()
        if type(now) not in (int, float) or math.isnan(now) or math.isinf(now) or now < self.last_time:
            raise RuntimeError('native CREW-ANY selector clock moved backwards')
        self.last_time = now
        if self.index >= len(self.targets):
            return True
        if type(self.window) is not dismissal._recruit_guard.window_class or not _unseated(self.window):
            raise RuntimeError('exact original unseated recruitment window required')
        name, target = self.targets[self.index]
        observed = dropdown_observation(self.window, name)
        if observed is None or target not in observed['options']:
            self.waits += 1
            self._fail_deadline(now)
            self.record('p04k_lifetime_selector_wait', name=name, target=target,
                        wait_count=self.waits, provider_ready=observed is not None,
                        target_available=False, original_surface='DropdownMenu.selectedIndex')
            return False
        if self.pending is not None:
            if now - self.pending['time'] < 1.0:
                return False
            if observed['selected_id'] != target:
                raise RuntimeError('native CREW-ANY selectedIndex readback differs from requested option')
            child_name, child_args = self._child(self.index, self.targets[2][1])
            events = dismissal._recruit_guard.selectors[self.pending['cursor']:]
            matches = [event for event in events
                       if event['owner_id'] == id(self.window) and event['method'] == child_name
                       and event['arguments'] == child_args and event['original_callback_returned'] is True]
            required = self.pending['changed'] and child_name is not None
            if required and len(matches) != 1:
                if not matches and now - self.pending['time'] < 3:
                    return False
                raise RuntimeError('changed CREW-ANY selector did not produce one original callback')
            proof = dict(name=name, target=target, changed=self.pending['changed'],
                         callback_required=required, callback=copy.deepcopy(matches[0]) if required else None)
            self.record('p04k_lifetime_selector_observed', observation=observed,
                        owner_id=id(self.window), proof=proof,
                        original_surface='DropdownMenu.selectedIndex')
            self.pending = None
            self.index += 1
            return self.index == len(self.targets)
        self.record('p04k_lifetime_selector_action', name=name, target=target,
                    before=observed, owner_id=id(self.window),
                    original_surface='DropdownMenu.selectedIndex')
        self.pending = dict(time=now, changed=observed['selected_id'] != target,
                            cursor=len(dismissal._recruit_guard.selectors))
        dropdown = getattr(self.window.flashObject, name)
        dropdown.selectedIndex = observed['option_indices'][observed['options'].index(target)]
        return False


class CatalogCommandTracker(object):
    """Bound one native CMD303 request to its typed proxy/update ordering."""
    def __init__(self, layout, identity, expect_result=0):
        if (type(layout) is not list or len(layout) != 4 or layout[0] != SHOP_REVISION
                or layout[3] != 0 or type(identity) is not int or not 4 <= identity <= LIFETIME_REJECT
                or expect_result not in (0, -10)):
            raise ValueError('bounded CREW-ANY CMD303 tracker arguments required')
        self.layout, self.identity, self.expect_result = list(layout), identity, expect_result
        self.request, self.update, self.success, self.proxy = None, None, None, []

    def observe(self, fields):
        event = fields.get('event')
        if event == 'p04k_native_barracks_request':
            raw = fields.get('layout')
            if (self.request is not None or fields.get('native_cmd') != 303
                    or type(raw) is not list or len(raw) != 4
                    or raw[1:] != self.layout[1:] or raw[0] not in (self.layout[0], 5)):
                raise ValueError('unexpected or repeated CREW-ANY CMD303 request')
            # Profile13's native shop publishes revision 5; the gateway
            # normalizes that one wire revision to the P04K internal 3.
            self.request = dict(fields, raw_layout=list(raw), layout=list(self.layout)); return
        if event == 'p09d_native_ammo_call' and fields.get('method') == '_update' and fields.get('phase') == 'return':
            if self.expect_result != 0 or self.request is None or self.update is not None:
                raise ValueError('unexpected CREW-ANY update before/after reject')
            old = integer(fields.get('previous_revision'), 1, 2147483646)
            if integer(fields.get('revision'), 2, 2147483647) != old + 1:
                raise ValueError('CREW-ANY update cursor differs')
            self.update = dict(fields); return
        if event == 'p04k_native_barracks_proxy':
            if self.request is None or fields.get('request_id') != self.request.get('request_id'):
                raise ValueError('CREW-ANY proxy has no matching request')
            if fields.get('phase') not in ('call', 'return') or len(self.proxy) >= 2:
                raise ValueError('CREW-ANY proxy phase/order differs')
            if fields.get('result') != self.expect_result:
                raise ValueError('CREW-ANY CMD303 result differs')
            if self.expect_result == 0 and fields.get('inventory_id') != self.identity:
                raise ValueError('CREW-ANY success identity differs')
            if self.expect_result != 0 and (fields.get('inventory_id') is not None or fields.get('inventory_matches') is not False):
                raise ValueError('CREW-ANY reject must carry no inventory extension')
            self.proxy.append(dict(fields)); return
        if event == 'p09d_native_ammo_call' and fields.get('method') == 'onCmdResponseExt' and fields.get('phase') == 'return':
            if self.request is None or fields.get('requestID') != self.request.get('request_id'):
                return
            if fields.get('resultID') != self.expect_result or self.success is not None:
                raise ValueError('CREW-ANY original callback result/order differs')
            self.success = dict(fields)

    def done(self):
        if self.request is None or self.success is None or len(self.proxy) != 2:
            return False
        if self.expect_result == 0 and self.update is None:
            return False
        return True

    def receipt(self):
        if not self.done():
            raise RuntimeError('CREW-ANY CMD303 tracker incomplete')
        return dict(native_cmd=303, layout=list(self.layout), identity=self.identity,
                    result=self.expect_result, proxy_count=len(self.proxy),
                    update_before_success=self.expect_result == 0)


def recruit_window_evidence(window, snapshot, vehicle, role):
    if not _unseated(window) or window is not dismissal._recruit_guard.window:
        raise RuntimeError('original unseated RecruitWindow required')
    dismissal._recruit_guard._mask(window, snapshot)
    choices = [dropdown_observation(window, name) for name in
               ('nationDropdown', 'vehicleClassDropdown', 'vehicleTypeDropdown', 'roleDropdown')]
    if any(choice is None for choice in choices) or [choice['selected_id'] for choice in choices] != [0, VEHICLES[vehicle][2], VEHICLES[vehicle][1], role]:
        raise RuntimeError('actual original recruitment selections differ')
    flash = window.flashObject
    label = flash.btnCourses.typeLabel.text
    if label != roster.LABEL % snapshot['free_quota']:
        raise RuntimeError('native free50 quota label differs')
    return dict(owner_id=id(window), current_vehicle_id=-1, menu_enabled=True, slot=None,
                selections=choices, label=label, free_quota=snapshot['free_quota'], role_level=50,
                paid_mask_requested=True, original_selector_callbacks=[copy.deepcopy(event)
                    for event in dismissal._recruit_guard.selectors if event['owner_id'] == id(window)], shop=native_shop())


FILTERS = (('all', (-1, 'None', 'None', 'None', None)),
           ('barracks', (-1, 'None', 'None', 'barracks', None)),
           ('gunner', (-1, 'gunner', 'None', 'None', None)))


def barracks_observation(snapshot, filter_name, require_purchase=False):
    if _guard is None or _guard.current is None or _guard.model is None:
        raise RuntimeError('native original Barracks list is unavailable')
    model = copy.deepcopy(_guard.model)
    rows = snapshot['tankmen']
    expected = [row['inventory_id'] for row in rows if
                (filter_name != 'barracks' or row['vehicle_inventory_id'] == -1)
                and (filter_name != 'gunner' or row['role'] == 'gunner')]
    if (filter_name not in dict(FILTERS) or sorted(model['row_ids']) != sorted(expected)
            or model['total'] != len(rows) or model['capacity'] != 16
            or model['unassigned'] != sum(row['vehicle_inventory_id'] == -1 for row in rows)
            or model['filter'] != dict(zip(('nation', 'role', 'tankType', 'location', 'nationID'), dict(FILTERS)[filter_name]))):
        raise RuntimeError('original Barracks filter/counts differ from actual inventory')
    tile = _guard.current.flashObject.form.tankmenTileList
    purchase = []
    visible = []
    renderers, layout = _logical_renderers(tile, model)
    if not layout['ready']:
        raise RuntimeError('original Barracks logical renderer data is not ready')
    for index, renderer, data in renderers:
        if _field(data, 'buy') is True:
            label = renderer.descrField.text
            if label != BERTH_NOTICE:
                raise RuntimeError('visible unsupported berth purchase reason differs')
            raw = dict(enabled=renderer.enabled, price_visible=renderer.price.visible,
                       action_price_visible=renderer.actionPrice.visible, count_visible=renderer.countField.visible)
            if any(type(value) is not bool for value in raw.values()):
                raise ValueError('native renderer boolean observation type differs')
            purchase.append(dict(index=dismissal.callback_integer(renderer.index, 0, 17), label=label,
                                 raw_boolean_observations=raw, boolean_readback='OBSERVATION_ONLY'))
        elif _field(data, 'tankmanID') is not None:
            visible.append(dismissal.callback_integer(_field(data, 'tankmanID'), 1, 16))
    if len(purchase) > 1 or require_purchase and len(purchase) != 1:
        raise RuntimeError('one visible source-defined purchase card required')
    model.update(filter_name=filter_name, visible_ids=visible, purchase=purchase, shop=native_shop(),
                 mask_applications=_guard.paint_count, owner_id=id(_guard.current), renderer_layout=layout)
    return model


class _Screenshots(recruitment._Screenshots):
    def capture(self, name, record):
        allowed = ('p04k_initial', 'p04k_barracks_initial', 'p04k_window_12', 'p04k_window_13',
                   'p04k_after_12', 'p04k_after_13', 'p04k_filter_all', 'p04k_filter_barracks',
                   'p04k_filter_gunner', 'p04k_relogin_ms1', 'p04k_relogin_is7', 'p04k_failure_barracks')
        if name not in allowed:
            raise ValueError('bounded Barracks screenshot basename required')
        if name not in self.requested:
            if any(entry.startswith(name + '_') for entry in self._entries()):
                raise ValueError('Barracks screenshot basename occupied')
            import BigWorld
            self.requested.add(name)
            BigWorld.screenShot('png', name)
            record('p04k_barracks_screenshot_requested', basename=name, writer='BigWorld.screenShot')
        names = [entry for entry in self._entries() if re.match(r'\A' + re.escape(name) + r'_[0-9]{3,10}\.png\Z', entry)]
        if not names:
            return None
        if len(names) != 1:
            raise ValueError('ambiguous native Barracks screenshot')
        from project_preferences import owned
        from ms1_crew_scenario import png_evidence
        path = owned(os.path.join(self.directory, names[0]), self.directory)
        if not os.path.isfile(path) or os.path.islink(path):
            raise ValueError('owned regular native screenshot required')
        return png_evidence(path, name)


class NativeScenario(transfer.NativeScenario):
    def __init__(self, record, mode, expected, hires=None, settings=None, clock=None):
        global _scenario
        if crew_vehicles.enabled():
            raise RuntimeError('P04K evidence scenarios are MS-1/IS-7 only; unavailable with CREW-ANY')
        if not callable(record) or mode not in ('recruit', 'relogin'):
            raise ValueError('explicit bounded Barracks mode required')
        self.expected = checked_expected(expected, ROLE_LEVEL)
        base_ids = [1, 2, 4, 6, 7, 8, 9, 10, 11]
        if (self.expected['selected_inventory_id'] != 1 or self.expected['ms1_crew'] != [4, 11]
                or self.expected['is7_crew'] != [6, 7, 8, 10, 9]
                or sorted(dismissal.member_map(self.expected)) != base_ids + ([] if mode == 'recruit' else [12, 13])
                or self.expected['free_quota'] != (5 if mode == 'recruit' else 3)):
            raise ValueError('exact accepted J or completed K sparse roster required')
        self.hires = checked_hires(hires) if mode == 'recruit' else None
        if mode == 'relogin' and hires is not None:
            raise ValueError('read-only relogin cannot carry hire catalog')
        self.record, self.mode = record, mode
        self.clock = clock if clock is not None else time.monotonic if hasattr(time, 'monotonic') else time.clock
        self.started = self.clock()
        self.last_time, self.advances, self.phase = self.started, 0, 'wait_hangar'
        self.error, self.pending, self.snapshot, self.ammo = None, None, None, None
        self.ready_since, self.selection_ready = None, None
        self.step, self.filter_index, self.selector_index = 0, 0, 0
        self.selected, self.views, self.captures, self.selector_pending = 1, [], [], None
        self.selector_receipts = []
        self.screenshots = None if settings is None else _Screenshots(settings)
        if _scenario is not None and _scenario.phase not in ('complete', 'error'):
            raise RuntimeError('one native Barracks diagnostic permitted')
        _scenario = self

    def emit(self, event, **fields):
        fields.update(version=VERSION, policy=POLICY, mode=self.mode, step=self.step)
        if 'snapshot' in fields:
            fields.update(native_descriptor_parse_repack=True, native_descriptor_count=len(fields['snapshot']['tankmen']))
        self.record(event, **fields)

    def _capture(self, name):
        if self.last_time - self.ready_since > 20:
            raise RuntimeError('Barracks screenshot deadline exceeded')
        if self.last_time - self.ready_since < 2:
            return False
        capture = None if self.screenshots is None else self.screenshots.capture(name, self.record)
        if self.screenshots is not None and capture is None:
            return False
        if capture is not None:
            self.captures.append(capture)
            self.emit('p04k_barracks_screenshot', screenshot=capture)
        return True

    def _unchanged(self):
        if native_snapshot(ROLE_LEVEL) != self.snapshot or cross.native_ammunition() != self.ammo:
            raise RuntimeError('native persistent state changed outside the expected303 transition')

    def _navigate(self, header, alias):
        self.emit('p04k_barracks_navigation', alias=alias, original_callback='LobbyHeader.menuItemClick')
        header.menuItemClick(alias)

    def _filter(self, page, index):
        name, args = FILTERS[index]
        self.emit('p04k_barracks_filter_action', name=name, arguments=list(args), original_callback='Barracks.setFilter')
        page.setFilter(*args)
        self.ready_since = self.last_time

    def _advance(self, ready):
        if self.phase == 'wait_hangar' and not ready:
            return False
        from gui.WindowsManager import g_windowsManager
        from gui.Scaleform.framework import ViewTypes
        from gui.Scaleform.daapi.settings.views import VIEW_ALIAS
        from gui.Scaleform.framework.managers.containers import POP_UP_CRITERIA
        from gui.Scaleform.Waiting import Waiting
        from CurrentVehicle import g_currentVehicle
        manager = g_windowsManager.window.containerManager
        lobby = manager.getContainer(ViewTypes.VIEW).getView()
        page = manager.getContainer(ViewTypes.LOBBY_SUB).getView()
        if lobby is None or lobby.flashObject is None or Waiting.isVisible():
            return False
        header = lobby.components['lobbyHeader']
        if _guard is None or _guard.error is not None:
            raise RuntimeError('native Barracks guard failed or is unavailable')
        if self.phase == 'wait_hangar':
            page.tankCarousel.vehicleChange(1)
            self.phase, self.ready_since = 'initial_wait', self.last_time
            return False
        if g_currentVehicle.invID != self.selected:
            if self.phase in ('initial_wait', 'hangar_wait', 'hangar_open'):
                if self.phase == 'hangar_open' and type(page).__name__ == 'Hangar':
                    page.tankCarousel.vehicleChange(self.selected)
                    self.phase, self.ready_since = 'hangar_wait', self.last_time
                return False
            raise RuntimeError('selected native vehicle changed during Barracks scenario')
        if self.phase == 'initial_wait':
            if not ready or self.last_time - self.ready_since < 2:
                return False
            self.snapshot, self.ammo = native_snapshot(ROLE_LEVEL), cross.native_ammunition()
            if self.snapshot != self.expected:
                raise RuntimeError('native initial roster differs from immutable oracle')
            self.emit('p04k_barracks_initial', snapshot=self.snapshot, ammunition=self.ammo, shop=native_shop(),
                      retired_absent=dismissal.retired_absence(self.snapshot))
            self.phase, self.ready_since = 'initial_capture', self.last_time
        if self.phase == 'initial_capture':
            self._unchanged()
            if not self._capture('p04k_initial'):
                return False
            self._navigate(header, VIEW_ALIAS.LOBBY_BARRACKS)
            self.phase = 'barracks_wait'
            return False
        if self.phase == 'barracks_wait':
            if type(page).__name__ != 'Barracks' or page is not _guard.current:
                return False
            self._unchanged()
            self._filter(page, 0)
            self.phase = 'barracks_capture'
            return False
        if self.phase.startswith('hangar_'):
            if type(page).__name__ != 'Hangar' or not ready:
                return False
            if self.phase == 'hangar_open':
                page.tankCarousel.vehicleChange(self.selected)
                self.phase, self.ready_since = 'hangar_wait', self.last_time
                return False
            if self.last_time - self.ready_since < 2:
                return False
            expected = dict(self.expected, selected_inventory_id=self.selected)
            actual = native_snapshot(ROLE_LEVEL)
            if actual != expected or cross.native_ammunition() != self.ammo:
                raise RuntimeError('fresh native vehicle selection changed persisted roster/ammunition')
            self.snapshot = actual
            if not self._capture('p04k_relogin_' + ('ms1' if self.selected == 1 else 'is7')):
                return False
            self.views.append(self.selected)
            self.emit('p04k_barracks_relogin_view', vehicle=self.selected, snapshot=actual,
                      readiness=dismissal.native_readiness(actual), efficiency=dismissal.native_efficiency(actual))
            if self.selected == 2:
                self.selected = 1
                page.tankCarousel.vehicleChange(1)
                self.ready_since = self.last_time
                return False
            self.emit('p04k_barracks_relogin', snapshot=actual, ammunition=self.ammo, operations=0,
                      vehicles_observed=self.views, exact_snapshot_match=True,
                      retired_absent=dismissal.retired_absence(actual), shop=native_shop())
            self.phase = 'complete'
            return True
        if type(page).__name__ != 'Barracks' or page is not _guard.current:
            raise RuntimeError('original Barracks owner changed during scenario')
        if self.phase == 'barracks_capture':
            self._unchanged()
            if self.last_time - self.ready_since < 2:
                return False
            unused, layout = _logical_renderers(page.flashObject.form.tankmenTileList, _guard.model)
            if not layout['ready']:
                self.emit('p04k_barracks_failure_surface', observation=layout, acceptance='FAIL_PENDING_CAPTURE')
                if not self._capture('p04k_failure_barracks'):
                    return False
                raise RuntimeError('original Barracks logical renderer data is not ready after failure capture')
            model = barracks_observation(self.snapshot, 'all')
            page.flashObject.form.tankmenTileList.scrollToIndex(len(model['row_ids']) + 1)
            self.phase, self.ready_since = 'purchase_capture', self.last_time
            return False
        if self.phase == 'purchase_capture':
            self._unchanged()
            if self.last_time - self.ready_since < 2:
                return False
            _guard.paint()
            model = barracks_observation(self.snapshot, 'all', True)
            if not self._capture('p04k_barracks_initial'):
                return False
            self.emit('p04k_barracks_observed', observation=model, snapshot=self.snapshot, stage='initial')
            self.phase = 'open' if self.mode == 'recruit' else 'filter_begin'
            return False
        window = manager.getContainer(ViewTypes.WINDOW).getView(criteria={POP_UP_CRITERIA.VIEW_ALIAS: VIEW_ALIAS.RECRUIT_WINDOW})
        if self.phase == 'open':
            self._unchanged()
            if window is not None:
                raise RuntimeError('unexpected recruitment window before original Barracks action')
            self.emit('p04k_barracks_before', name=STEPS[self.step][0], snapshot=self.snapshot, ammunition=self.ammo, shop=native_shop())
            page.onShowRecruitWindowClick(None, True)
            self.phase, self.ready_since, self.selector_index, self.selector_pending = 'selectors', self.last_time, 0, None
            self.selector_receipts = []
            return False
        if self.phase == 'selectors':
            self._unchanged()
            if window is None or window.flashObject is None:
                return False
            if type(window) is not dismissal._recruit_guard.window_class or not _unseated(window):
                raise RuntimeError('exact original unseated recruitment window required')
            if self.last_time - self.ready_since > 25:
                raise RuntimeError('native original selector event chain deadline exceeded')
            vehicle, role = STEPS[self.step][1:3]
            choices = (('nationDropdown', 0), ('vehicleClassDropdown', VEHICLES[vehicle][2]),
                       ('vehicleTypeDropdown', VEHICLES[vehicle][1]), ('roleDropdown', role))
            name, target = choices[self.selector_index]
            observed = dropdown_observation(window, name)
            if observed is None or target not in observed['options']:
                return False
            if self.selector_pending is not None:
                if self.last_time - self.selector_pending['time'] < 1:
                    return False
                if observed['selected_id'] != target:
                    raise RuntimeError('native selectedIndex readback differs from requested original option')
                child = (('updateVehicleClassDropdown', [0]),
                         ('updateVehicleTypeDropdown', [0, VEHICLES[vehicle][2]]),
                         ('updateRoleDropdown', [0, VEHICLES[vehicle][2], VEHICLES[vehicle][1]]),
                         (None, None))[self.selector_index]
                matches = [event for event in dismissal._recruit_guard.selectors[self.selector_pending['cursor']:]
                           if event['owner_id'] == id(window) and event['method'] == child[0]
                           and event['arguments'] == child[1] and event['original_callback_returned'] is True]
                required = self.selector_pending['changed'] and child[0] is not None
                if required and len(matches) != 1:
                    if not matches and self.last_time - self.selector_pending['time'] < 3:
                        return False
                    raise RuntimeError('changed selector did not produce exactly one matching original callback')
                proof = dict(name=name, changed=self.selector_pending['changed'], callback_required=required,
                             callback=copy.deepcopy(matches[0]) if required else None)
                self.selector_receipts.append(proof)
                self.emit('p04k_barracks_selector_observed', observation=observed, owner_id=id(window), proof=proof)
                self.selector_pending = None
                self.selector_index += 1
                if self.selector_index == 4:
                    self.phase, self.ready_since = 'window_capture', self.last_time
                return False
            self.emit('p04k_barracks_selector_action', name=name, target=target, before=observed, owner_id=id(window),
                      original_surface='DropdownMenu.selectedIndex')
            self.selector_pending = dict(time=self.last_time, changed=observed['selected_id'] != target,
                                         cursor=len(dismissal._recruit_guard.selectors))
            position = observed['options'].index(target)
            getattr(window.flashObject, name).selectedIndex = observed.get('option_indices', observed['options'])[position]
            return False
        if self.phase == 'window_capture':
            self._unchanged()
            if window is None:
                raise RuntimeError('original recruit window disappeared before submit')
            vehicle, role, identity = STEPS[self.step][1:]
            observation = recruit_window_evidence(window, self.snapshot, vehicle, role)
            if not self._capture('p04k_window_' + str(identity)):
                return False
            self.emit('p04k_barracks_window', observation=observation, selector_proofs=self.selector_receipts, snapshot=self.snapshot)
            layout = [3, VEHICLES[vehicle][0], ROLES[role], 0]
            self.pending = dict(tracker=NativeCommandTracker(layout, self.hires[self.step]),
                                expected=projected_hire(self.snapshot, self.hires[self.step]))
            args = [0, VEHICLES[vehicle][1], role, 0, None]
            self.phase = 'wait_result'
            self.emit('p04k_barracks_action', name=STEPS[self.step][0], native_cmd=303, layout=layout,
                      arguments=args, original_callback='RecruitWindow.buyTankman')
            window.buyTankman(*args)
            return False
        if self.phase == 'wait_result':
            tracker = self.pending['tracker']
            if tracker.success is None:
                return False
            actual = native_snapshot(ROLE_LEVEL)
            if actual != self.pending['expected'] or cross.native_ammunition() != self.ammo:
                raise RuntimeError('actual303 update differs from immutable expected hire')
            self.snapshot = actual
            self.emit('p04k_barracks_callback', **tracker.receipt())
            self.emit('p04k_barracks_after', name=STEPS[self.step][0], snapshot=actual, ammunition=self.ammo,
                      shop=native_shop(), retired_absent=dismissal.retired_absence(actual))
            self.phase, self.ready_since = 'after_capture', self.last_time
            return False
        if self.phase == 'after_capture':
            self._unchanged()
            if window is not None:
                return False
            model = barracks_observation(self.snapshot, 'all')
            if not self._capture('p04k_after_' + str(STEPS[self.step][3])):
                return False
            self.emit('p04k_barracks_observed', observation=model, snapshot=self.snapshot, stage='after')
            self.step, self.pending = self.step + 1, None
            self.phase = 'open' if self.step < 2 else 'filter_begin'
            return False
        if self.phase == 'filter_begin':
            self._unchanged()
            self._filter(page, self.filter_index)
            page.flashObject.form.tankmenTileList.scrollToIndex(0)
            self.phase = 'filter_capture'
            return False
        if self.phase == 'filter_capture':
            self._unchanged()
            name = FILTERS[self.filter_index][0]
            model = barracks_observation(self.snapshot, name)
            if not self._capture('p04k_filter_' + name):
                return False
            self.emit('p04k_barracks_filter_observed', observation=model, snapshot=self.snapshot)
            self.filter_index += 1
            if self.filter_index < len(FILTERS):
                self.phase = 'filter_begin'
                return False
            if self.mode == 'recruit':
                self.emit('p04k_barracks_final', snapshot=self.snapshot, ammunition=self.ammo, operations=2,
                          shop=native_shop(), retired_absent=dismissal.retired_absence(self.snapshot),
                          readiness=dismissal.native_readiness(self.snapshot), efficiency=dismissal.native_efficiency(self.snapshot))
                self.phase = 'complete'
                return True
            self.selected = 2
            self._navigate(header, VIEW_ALIAS.LOBBY_HANGAR)
            self.phase, self.ready_since = 'hangar_open', self.last_time
            return False
        return False


class CatalogLifetimeScenario(object):
    """Bounded native CREW-ANY loop for T-26 identities 18..192 + #193.

    The server remains authoritative.  This state machine only opens the
    original Barracks window, drives its public DropdownMenu selectedIndex,
    and waits for the original CMD303 proxy/update ordering.  When the 16
    original berths fill up it pauses in ``await_dismissal``; a separate
    original CMD306 path must free one berth before the loop resumes.
    """
    def __init__(self, record, expected=None, settings=None, clock=None):
        global _scenario
        if not callable(record) or not crew_vehicles.enabled():
            raise ValueError('CREW-ANY lifetime requires the enabled catalog table')
        if expected is not None:
            expected = dismissal.checked_expected(expected, ROLE_LEVEL)
        self.record, self.mode = record, 'lifetime'
        self.expected = expected
        self.clock = clock if clock is not None else time.monotonic if hasattr(time, 'monotonic') else time.clock
        self.started = self.last_time = self.clock()
        self.last_time = self.started
        self.phase, self.advances, self.error = 'wait_hangar', 0, None
        self.snapshot, self.ammo = None, None
        self.ready_since, self.selected = None, None
        self.next_identity, self.successes = LIFETIME_FIRST, 0
        self.pending, self.selector = None, None
        self.dismissal_seen, self.dismiss_identity = 0, None
        self.dismissal_proxy_tracker = None
        self.dismissal_proxy_previous = None
        if _scenario is not None and _scenario.phase not in ('complete', 'error'):
            raise RuntimeError('one native Barracks diagnostic permitted')
        _scenario = self

    def emit(self, event, **fields):
        fields.update(version=VERSION, policy=POLICY, mode='lifetime',
                     next_identity=self.next_identity, successes=self.successes)
        self.record(event, **fields)

    def _assert_unchanged(self):
        if self.snapshot is None:
            return
        actual = native_snapshot(ROLE_LEVEL)
        if actual != self.snapshot or cross.native_ammunition() != self.ammo:
            raise RuntimeError('CREW-ANY persistent state changed outside expected CMD303/CMD306')

    @staticmethod
    def _window(manager, ViewTypes, POP_UP_CRITERIA, VIEW_ALIAS):
        return manager.getContainer(ViewTypes.WINDOW).getView(
            criteria={POP_UP_CRITERIA.VIEW_ALIAS: VIEW_ALIAS.RECRUIT_WINDOW})

    def _catalog_vehicle(self):
        table = crew_vehicles.vehicles(None, self.snapshot)
        matches = [identity for identity, row in table.items() if row[1] == 18]
        if len(matches) != 1:
            raise RuntimeError('exact owned T-26 vehicle required for CREW-ANY lifetime')
        return matches[0]

    def _record_baseline(self):
        self.snapshot = native_snapshot(ROLE_LEVEL)
        self.ammo = cross.native_ammunition()
        if self.expected is not None and self.snapshot != self.expected:
            raise RuntimeError('native CREW-ANY lifetime baseline differs from immutable expectation')
        identities = [row['inventory_id'] for row in self.snapshot['tankmen']]
        if (self.snapshot['free_quota'] != 175 or max(identities or [0]) != 17
                or len(identities) != 17):
            raise RuntimeError('native CREW-ANY lifetime requires clean v2 baseline #17/175')
        self.selected = self._catalog_vehicle()
        self.emit('p04k_lifetime_initial', snapshot=self.snapshot, ammunition=self.ammo,
                  vehicle_inventory_id=self.selected, target_type_id=18, target_role='driver')

    def _advance(self, ready_hangar):
        if self.phase == 'wait_hangar' and not ready_hangar:
            return False
        from gui.WindowsManager import g_windowsManager
        from gui.Scaleform.framework import ViewTypes
        from gui.Scaleform.daapi.settings.views import VIEW_ALIAS
        from gui.Scaleform.framework.managers.containers import POP_UP_CRITERIA
        from gui.Scaleform.Waiting import Waiting
        manager = g_windowsManager.window.containerManager
        lobby = manager.getContainer(ViewTypes.VIEW).getView()
        page = manager.getContainer(ViewTypes.LOBBY_SUB).getView()
        if lobby is None or lobby.flashObject is None or Waiting.isVisible():
            return False
        if _guard is None or _guard.error is not None:
            raise RuntimeError('CREW-ANY Barracks guard unavailable')
        window = self._window(manager, ViewTypes, POP_UP_CRITERIA, VIEW_ALIAS)
        personal = manager.getContainer(ViewTypes.WINDOW).getView(
            criteria={POP_UP_CRITERIA.VIEW_ALIAS: VIEW_ALIAS.PERSONAL_CASE})
        dialog = dismissal._dismiss_guard.current
        if self.phase == 'wait_hangar':
            self._record_baseline()
            page.tankCarousel.vehicleChange(self.selected)
            self.phase, self.ready_since = 'hangar_wait', self.last_time
            return False
        if self.phase == 'hangar_wait':
            if not ready_hangar or self.last_time - self.ready_since < 2:
                return False
            self._record_baseline()
            self.emit('p04k_lifetime_navigation', alias='barracks', original_callback='LobbyHeader.menuItemClick')
            lobby.components['lobbyHeader'].menuItemClick(VIEW_ALIAS.LOBBY_BARRACKS)
            self.phase = 'barracks_wait'
            return False
        if type(page).__name__ != 'Barracks' or page is not _guard.current:
            return False
        if self.phase == 'barracks_wait':
            page.setFilter(*FILTERS[0][1])
            self.phase, self.ready_since = 'refresh', self.last_time
            return False
        if self.phase == 'refresh':
            if self.last_time - self.ready_since < 2:
                return False
            self.snapshot = native_snapshot(ROLE_LEVEL)
            if self.snapshot['free_quota'] != 193 - self.next_identity:
                raise RuntimeError('native CREW-ANY quota cursor differs')
            unassigned = sum(row['vehicle_inventory_id'] == -1 for row in self.snapshot['tankmen'])
            if unassigned >= 16:
                candidates = sorted(row['inventory_id'] for row in self.snapshot['tankmen']
                                    if row['vehicle_inventory_id'] == -1)
                if not candidates:
                    raise RuntimeError('native CREW-ANY full berth has no dismissible member')
                self.dismiss_identity = candidates[0]
                self.pending = dict(tracker=dismissal.NativeCommandTracker(306, [self.dismiss_identity, 0, 0]),
                                    identity=self.dismiss_identity, expect=0)
                self.dismissal_proxy_tracker = dismissal.NativeCommandTracker(306, [self.dismiss_identity, 0, 0])
                self.dismissal_proxy_previous = dismissal._scenario
                dismissal._scenario = type('CatalogDismissalProxy', (), {
                    'mode': 'dismiss', 'preflight_active': False,
                    'pending': {'tracker': self.dismissal_proxy_tracker}, 'button_events': [], 'engine_input': {'stage': 'simple'},
                    'error': None})()
                self.phase = 'dismissal_personal'
                page.crewPanel.openPersonalCase(self.dismiss_identity, 2)
                self.emit('p04k_lifetime_need_dismissal', unassigned=unassigned,
                          berth_capacity=16, native_cmd=306, identity=self.dismiss_identity,
                          original_callback='Crew.openPersonalCase', original_callback_required=True)
                return False
            if self.next_identity <= LIFETIME_LAST:
                self.phase = 'open'
            else:
                self.phase = 'reject_open'
            return False
        if self.phase == 'dismissal_personal':
            if personal is None or personal.flashObject is None:
                return False
            if (type(personal) is not dismissal._personal_guard.window_class
                    or personal.tmanInvID != self.dismiss_identity):
                raise RuntimeError('exact original PersonalCase required for bounded CMD306')
            dismissal._personal_guard.mask(personal)
            if not all(key in dismissal._personal_guard.models[personal] for key in ('common', 'skills', 'dossier')):
                return False
            personal.dismissTankman(self.dismiss_identity)
            self.phase = 'dismissal_dialog'
            return False
        if self.phase == 'dismissal_dialog':
            if dialog is None or dialog.flashObject is None:
                return False
            observed = dismissal.confirmation_observation(dialog)
            if observed is None:
                return False
            if (observed['inventory_id'] != self.dismiss_identity or observed['protected']
                    or observed['input_visible']):
                raise RuntimeError('simple50 original confirmation differs for bounded CMD306')
            dismissal.focus_confirmation_submit(dialog, self.record)
            self.emit('p04k_lifetime_dismissal_action', native_cmd=306,
                      layout=[self.dismiss_identity, 0, 0], original_callback='GUI.handleKeyEvent',
                      arguments=['KEY_RETURN', 'down', 'up'], dialog_owner_id=id(dialog))
            dismissal.send_engine_return(dialog, 'simple', self.record)
            self.phase = 'dismissal_wait'
            return False
        if self.phase == 'dismissal_wait':
            if (self.pending is None or not self.pending['tracker'].done()
                    or self.dismissal_proxy_tracker is None or not self.dismissal_proxy_tracker.done()):
                return False
            before = self.snapshot
            actual = native_snapshot(ROLE_LEVEL)
            if actual == before or self.dismiss_identity in {row['inventory_id'] for row in actual['tankmen']}:
                raise RuntimeError('CMD306 completed without removing the bounded member')
            self.snapshot, self.dismissal_seen = actual, self.dismissal_seen + 1
            unassigned = sum(row['vehicle_inventory_id'] == -1 for row in actual['tankmen'])
            if unassigned >= 16:
                raise RuntimeError('CMD306 did not free a bounded original berth')
            self.emit('p04k_lifetime_dismissal_observed', native_cmd=306,
                      dismissal_count=self.dismissal_seen, identity=self.dismiss_identity,
                      receipt=self.pending['tracker'].receipt(),
                      original_dismissal_receipt=self.dismissal_proxy_tracker.receipt(), unassigned=unassigned)
            dismissal._scenario = self.dismissal_proxy_previous
            self.dismissal_proxy_previous = None
            self.pending, self.dismiss_identity, self.dismissal_proxy_tracker = None, None, None
            self.phase, self.ready_since = 'refresh', self.last_time
            return False
        if self.phase in ('open', 'reject_open'):
            if window is not None:
                raise RuntimeError('unexpected RecruitWindow before original Barracks action')
            self.emit('p04k_lifetime_before', identity=self.next_identity,
                      target_type_id=18, target_role='driver', shop=native_shop())
            page.onShowRecruitWindowClick(None, True)
            self.selector = None
            self.phase, self.ready_since = ('reject_selectors' if self.phase == 'reject_open' else 'selectors'), self.last_time
            return False
        if self.phase in ('selectors', 'reject_selectors'):
            if window is None or window.flashObject is None:
                return False
            if type(window) is not dismissal._recruit_guard.window_class or not _unseated(window):
                raise RuntimeError('exact original CREW-ANY RecruitWindow required')
            if self.selector is None:
                self.selector = BoundedCatalogSelectorController(self.record, window, 18, 'driver', clock=self.clock)
            if self.selector.advance():
                self.phase = 'reject_wait_result' if self.phase == 'reject_selectors' else 'submit'
            return False
        if self.phase in ('submit', 'reject_wait_result'):
            if window is None:
                return False
            identity = LIFETIME_REJECT if self.phase == 'reject_wait_result' else self.next_identity
            expect = -10 if identity == LIFETIME_REJECT else 0
            tracker = CatalogCommandTracker([SHOP_REVISION, 4609, 3, 0], identity, expect_result=expect)
            self.pending = dict(tracker=tracker, identity=identity, expect=expect)
            self.phase = 'wait_result'
            self.emit('p04k_lifetime_action', identity=identity, native_cmd=303,
                      layout=[SHOP_REVISION, 4609, 3, 0], original_callback='RecruitWindow.buyTankman')
            # RecruitWindow.buyTankman receives the source type id; original
            # Shop.buyTankman expands it to compact 4609 in CMD303.
            window.buyTankman(0, 18, 'driver', 0, None)
            return False
        if self.phase == 'wait_result':
            if self.pending is None or not self.pending['tracker'].done():
                return False
            identity, expect = self.pending['identity'], self.pending['expect']
            actual = native_snapshot(ROLE_LEVEL)
            if expect == 0:
                rows = {row['inventory_id']: row for row in actual['tankmen']}
                row = rows.get(identity)
                if (row is None or row['vehicle_type_id'] != 18 or row['role'] != 'driver'
                        or row['vehicle_inventory_id'] != -1 or actual['free_quota'] != 192 - identity):
                    raise RuntimeError('native CREW-ANY CMD303 success state differs')
                self.snapshot = actual; self.successes += 1; self.next_identity += 1
                self.emit('p04k_lifetime_callback', receipt=self.pending['tracker'].receipt(), snapshot=actual)
                self.pending = None
                self.phase, self.ready_since = 'refresh', self.last_time
                return False
            if actual != self.snapshot:
                raise RuntimeError('native CREW-ANY #193 rejection changed persistent state')
            self.emit('p04k_lifetime_reject', receipt=self.pending['tracker'].receipt(),
                      identity=LIFETIME_REJECT, free_quota=actual['free_quota'])
            self.phase, self.pending = 'complete', None
            return True
        if self.phase == 'complete':
            return True
        return False

    def advance(self, ready_hangar):
        if type(ready_hangar) is not bool:
            raise ValueError('explicit native Hangar readiness required')
        if self.phase == 'complete':
            return True
        if self.phase == 'error':
            raise RuntimeError(self.error or 'failed CREW-ANY lifetime scenario')
        try:
            now = self.clock()
            if (type(now) not in (int, float) or math.isnan(now) or math.isinf(now)
                    or now < self.last_time or now - self.started > LIFETIME_DEADLINE):
                raise RuntimeError('native CREW-ANY lifetime deadline exceeded')
            self.last_time, self.advances = now, self.advances + 1
            if self.advances > 12000:
                raise RuntimeError('native CREW-ANY lifetime observation budget exhausted')
            if self.error is not None:
                raise RuntimeError(self.error)
            return self._advance(ready_hangar)
        except Exception:
            if self.dismissal_proxy_previous is not None:
                dismissal._scenario = self.dismissal_proxy_previous
                self.dismissal_proxy_previous = None
            self.phase = 'error'
            raise
