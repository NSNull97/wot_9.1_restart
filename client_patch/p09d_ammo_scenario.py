# -*- coding: utf-8 -*-
"""Explicit seven-step native service diagnostic; no client inventory writes.

This is programmatic invocation of original GUI callbacks, not human/OS input.
The observed network update and original processor result are mandatory.
"""
import copy
import math

from account_switch_scenario import _Native as AccountNative, _keys
from ms1_crew_scenario import _integer, _now
import p09d_ammo_ui as ui

VERSION = 1
MAX_ADVANCES = 240
MAX_SECONDS = 210.0
PHASE_SECONDS = 30.0
INITIAL = ((42, 36, 18), (21, 9, 0))
OPERATIONS = ((1, (41, 35, 17), 'ms1_unload'),
              (1, (40, 30, 26), 'ms1_refill'),
              (2, (20, 8, 0), 'is7_unload'),
              (2, (18, 8, 4), 'is7_refill'),
              (1, INITIAL[0], 'ms1_restore'),
              (2, INITIAL[1], 'is7_restore'))
SCREENSHOTS = ('p09d_initial_ms1', 'p09d_initial_is7',
               'p09d_ms1_unload', 'p09d_ms1_refill', 'p09d_ms1_result',
               'p09d_is7_unload', 'p09d_is7_refill', 'p09d_is7_result',
               'p09d_ms1_restore', 'p09d_ms1_restored', 'p09d_is7_restore', 'p09d_is7_restored')
_expected = None
_scenario = None


def checked_expected(value):
    _keys(value, ('version', 'database_id', 'source_revision', 'initial'))
    _integer(value['version'], 1, 1)
    _integer(value['database_id'], 1, 2147483647)
    _integer(value['source_revision'], 7, 7)
    rows = value['initial']
    if type(rows) is not list or len(rows) != 2:
        raise ValueError('exact initial MS-1/IS-7 expectation required')
    for index, row in enumerate(rows):
        _keys(row, ('vehicle_id', 'loaded', 'depot'))
        _integer(row['vehicle_id'], index + 1, index + 1)
        if type(row['loaded']) is not list or tuple(row['loaded']) != INITIAL[index]:
            raise ValueError('reviewed native relogin starting quantities required')
        if type(row['depot']) is not list or len(row['depot']) != 3:
            raise ValueError('three authoritative depot expectations required')
        for n in row['loaded'] + row['depot']:
            _integer(n, 0, 1000000)
        for vehicle, counts, _ in OPERATIONS:
            if vehicle == index + 1 and any(n > old + spare for n, old, spare in
                                           zip(counts, row['loaded'], row['depot'])):
                raise ValueError('diagnostic requires sufficient owned stock')
    return copy.deepcopy(value)


def arm(value):
    global _expected
    if _expected is not None or _scenario is not None:
        raise RuntimeError('native service diagnostic may be armed only once')
    _expected = checked_expected(value)


def quantities(snapshot, vehicle, counts, depot):
    """Read real raw caches and independent native GUI shell getters."""
    type_cd = (3329, 7169)[vehicle - 1]
    turret, gun, capacity, shells = ui.MOUNTS[type_cd]
    if snapshot.get('supported') is not True or snapshot.get('mount') != {
            'vehicle_type_cd': type_cd, 'inventory_id': vehicle, 'turret_cd': turret,
            'gun_cd': gun, 'capacity': capacity, 'compatible_shells': list(shells)}:
        raise ValueError('actual selected original mounted configuration differs')
    loaded = ui.flat(snapshot['loaded'])
    layout = ui.flat(snapshot['layout'], signed=True)
    pairs = lambda flat: dict((abs(flat[i]), flat[i + 1]) for i in (0, 2, 4))
    expected = dict(zip(shells, counts))
    if pairs(loaded) != expected or pairs(layout) != expected:
        raise ValueError('native loaded/layout differs from authoritative expectation')
    if snapshot['depot'] != [[cd, n] for cd, n in zip(shells, depot)]:
        raise ValueError('actual native depot differs from conserved owned quantities')
    expected_gui = dict((cd, (n, n, stock)) for cd, n, stock in zip(shells, counts, depot))
    actual_gui = dict((row['shell_cd'], (row['count'], row['default_count'], row['inventory_count']))
                      for row in snapshot['gui_shells'])
    if len(snapshot['gui_shells']) != 3 or actual_gui != expected_gui:
        raise ValueError('actual original GUI shell getters differ from native raw cache')
    return copy.deepcopy(snapshot)


class _ShellRequest(object):
    """Transient arguments to original fillVehicle, never native inventory items."""
    def __init__(self, shell, count):
        self.compactDescr = shell.intCD
        self.prices = shell.buyPrice
        self.currency = 'credits'
        self.goldShellsForCredits = shell.isBoughtForCredits
        self.userCount = count


class _Native(AccountNative):
    def select(self, vehicle):
        self.state()
        from gui.WindowsManager import g_windowsManager
        from gui.Scaleform.framework import ViewTypes
        page = g_windowsManager.window.containerManager.getContainer(ViewTypes.LOBBY_SUB).getView()
        page.tankCarousel.vehicleChange(vehicle)

    def window(self):
        from gui.WindowsManager import g_windowsManager
        from gui.Scaleform.framework import ViewTypes
        from gui.Scaleform.framework.managers.containers import POP_UP_CRITERIA
        from gui.Scaleform.daapi.settings.views import VIEW_ALIAS
        from gui.Scaleform.daapi.view.lobby.hangar.TechnicalMaintenance import TechnicalMaintenance
        windows = g_windowsManager.window.containerManager.getContainer(ViewTypes.WINDOW)
        view = windows.getView(criteria={POP_UP_CRITERIA.VIEW_ALIAS: VIEW_ALIAS.TECHNICAL_MAINTENANCE})
        if view is not None:
            if type(view) is not TechnicalMaintenance or view.flashObject is None:
                raise RuntimeError('actual original maintenance is not Flash-bound')
            ui._audit_class(type(view))
        return view

    def open(self):
        if self.window() is not None:
            raise RuntimeError('previous native maintenance window remains open')
        from gui.WindowsManager import g_windowsManager
        from gui.Scaleform.framework import ViewTypes
        page = g_windowsManager.window.containerManager.getContainer(ViewTypes.LOBBY_SUB).getView()
        panel = page.components.get('ammunitionPanel')
        if panel is None or panel.flashObject is None:
            raise RuntimeError('actual original ammunition panel is unavailable')
        panel.showTechnicalMaintenance()

    def close(self):
        view = self.window()
        if view is None:
            raise RuntimeError('native maintenance result window missing')
        view.destroy()

    def snapshot(self):
        return ui.observe()

    def fill(self, vehicle, counts):
        from CurrentVehicle import g_currentVehicle
        view = self.window()
        if view is None or g_currentVehicle.invID != vehicle or ui.selection() is None:
            raise RuntimeError('original service owner or selection changed')
        shells = g_currentVehicle.item.shells
        cds = ui.MOUNTS[(3329, 7169)[vehicle - 1]][3]
        by_id = dict((shell.intCD, shell) for shell in shells)
        if set(by_id) != set(cds):
            raise RuntimeError('actual native shell collection changed')
        args = [_ShellRequest(by_id[cd], n) for cd, n in zip(cds, counts)]
        # Verified original no-purchase layout branch, offsets281-324. These
        # booleans are request arguments, not writes to GUI or account state.
        view.fillVehicle(False, False, False, False, False, False, args, [None, None, None])

    def request(self, basename):
        import BigWorld
        if basename not in SCREENSHOTS or basename in self.requested:
            raise ValueError('unsupported or repeated native service PNG')
        if any(name.startswith(basename + '_') for name in self._entries()):
            raise ValueError('native service PNG already exists')
        self.requested.add(basename)
        BigWorld.screenShot('png', basename)


class _Scenario(object):
    def __init__(self, settings, record, native=None, clock=None):
        if settings.get('enable_p09d_ammo_service') is not True or _expected is None or not callable(record):
            raise RuntimeError('explicit armed native service settings required')
        self.expected = checked_expected(_expected)
        self.native = _Native(settings) if native is None else native
        self.record, self.clock = record, _now if clock is None else clock
        self.phase, self.step, self.index = 'select_initial', 1, 0
        self.advances, self.started, self.phase_at, self.last_time = 0, None, None, None
        self.account, self.last_render, self.pending, self.error = None, None, None, None
        self.completed, self.png, self.screenshots, self.results = False, None, [], []
        self.counts = [list(v['loaded']) for v in self.expected['initial']]
        self.depots = [list(v['depot']) for v in self.expected['initial']]
        self.emit('p09d_scenario_start', expected=self.expected, steps=7,
                  operations=[{'vehicle':v, 'counts':list(c), 'name':n} for v,c,n in OPERATIONS],
                  computer_input=False, native_callback_invocation=True, inventory_state_injected=False,
                  native_pixels_review='NOT_RUN', human_manual_acceptance='NOT_RUN')

    def emit(self, event, **fields):
        fields.update(version=VERSION, phase=self.phase, step=self.step)
        self.record(event, **fields)

    def transition(self, phase, now):
        self.phase, self.phase_at = phase, now

    def state(self):
        state = self.native.state()
        if state['account']['database_id'] != self.expected['database_id']:
            raise RuntimeError('native diagnostic account identity differs')
        if self.account is None:
            self.account = copy.deepcopy(state['account'])
        elif state['account'] != self.account:
            raise RuntimeError('native identity/resources/fleet/crew/dossier changed')
        return state

    def observe(self, vehicle):
        snapshot = quantities(self.native.snapshot(), vehicle, self.counts[vehicle - 1], self.depots[vehicle - 1])
        self.emit('p09d_scenario_snapshot', vehicle=vehicle, snapshot=snapshot)
        return snapshot

    def native_event(self, fields):
        # Called only for the existing source-pinned passive observer. Never
        # raise inside sys.setprofile: preserve failure for the next advance.
        if self.completed or self.error:
            return
        try:
            method, phase = fields.get('method'), fields.get('phase')
            if method == 'as_setDataS' and phase == 'return':
                self.last_render = copy.deepcopy(fields)
            pending = self.pending
            if pending is None or pending['complete']:
                return
            if method == '__setAndFillLayouts_onShopSynced' and phase == 'return' and 'arguments' in fields:
                arr = fields['arguments']
                shells = ui.MOUNTS[(3329, 7169)[pending['vehicle'] - 1]][3]
                if (len(arr) != 16 or arr[:3] != [3, pending['vehicle'], 6] or arr[9:] != [6, 0, 0, 0, 0, 0, 0]
                        or [abs(arr[i]) for i in (3, 5, 7)] != list(shells)
                        or [arr[i] for i in (4, 6, 8)] != pending['counts'] or pending['request']):
                    raise RuntimeError('original native CMD108 arguments differ or repeated')
                pending['request'] = True
            if method == '_update' and phase == 'return' and fields.get('has_inventory'):
                if not pending['request'] or pending['update']:
                    raise RuntimeError('native inventory update precedes request or repeats')
                quantities(fields['snapshot'], pending['vehicle'], pending['counts'], pending['depot'])
                if fields.get('revision') != fields.get('previous_revision', -2) + 1:
                    raise RuntimeError('original native update revision does not advance once')
                pending['update'] = True
            if method == 'onCmdResponseExt' and phase == 'call':
                pending['response'] = fields.get('requestID')
                pending['processor'] = False
            if method == '_errorHandler':
                raise RuntimeError('original vehicle layout processor rejected service')
            if method == '_successHandler' and phase == 'return':
                if not pending['update'] or fields.get('code') != 0 or pending.get('response') is None:
                    raise RuntimeError('native layout success lacks preceding actual update')
                pending['processor'] = True
            if method == 'onCmdResponseExt' and phase == 'return' and pending.get('processor'):
                if fields.get('requestID') != pending['response'] or fields.get('resultID') != 0:
                    raise RuntimeError('native command callback identity/result differs')
                pending['complete'] = True
        except Exception as error:
            self.error = type(error).__name__ + ': ' + str(error)

    def capture(self, basename, now, next_phase):
        self.native.request(basename)
        self.png = (basename, next_phase)
        self.transition('wait_png', now)
        self.emit('p09d_scenario_screenshot_requested', basename=basename, writer='BigWorld.screenShot')

    def rendered(self, vehicle):
        view = self.native.window()
        row = self.last_render
        if view is None or row is None or row.get('owner_id') != id(view):
            return False
        if row.get('flash_bound') is not True or row.get('capacity') != (96, 30)[vehicle - 1]:
            raise RuntimeError('original maintenance render is not bound to expected mount')
        cds = ui.MOUNTS[(3329, 7169)[vehicle - 1]][3]
        actual = dict((v['compactDescr'], (v['count'], v['userCount'], v['inventoryCount'])) for v in row['shells'])
        expected = dict((cd, (n, n, d)) for cd, n, d in zip(cds, self.counts[vehicle - 1], self.depots[vehicle - 1]))
        if actual != expected or len(row['shells']) != 3:
            raise RuntimeError('original maintenance render quantities differ')
        return True

    def advance(self, observed, ready_hangar):
        if self.completed:
            return True
        if self.phase == 'error' or self.error:
            raise RuntimeError(self.error or 'failed scenario cannot resume')
        self.advances += 1
        now = self.clock()
        if type(now) not in (int, float) or math.isnan(now) or math.isinf(now) or (self.last_time is not None and now < self.last_time):
            raise ValueError('finite monotonic diagnostic clock required')
        self.last_time = now
        if self.started is None:
            self.started, self.phase_at = now, now
        if self.advances > MAX_ADVANCES or now - self.started > MAX_SECONDS or now - self.phase_at > PHASE_SECONDS:
            raise RuntimeError('bounded native service scenario timed out')
        if type(observed) is not dict or type(ready_hangar) is not bool:
            raise ValueError('original observed readiness required')
        if not ready_hangar:
            return False
        current = self.state()
        if self.phase == 'wait_png':
            proof = self.native.screenshot(self.png[0])
            if proof is None:
                return False
            if proof.get('basename') != self.png[0] or proof.get('png_container_valid') is not True:
                raise RuntimeError('bounded native PNG evidence missing')
            self.screenshots.append(proof)
            self.emit('p09d_scenario_screenshot', screenshot=proof)
            self.transition(self.png[1], now)
            self.png = None
            return False
        if self.phase == 'select_initial':
            self.native.select(self.index + 1)
            self.transition('initial', now)
            return False
        if self.phase == 'initial':
            vehicle = self.index + 1
            if current['selected_inventory_id'] != vehicle or observed.get('vehicle_model_loaded') is not True:
                return False
            self.observe(vehicle)
            self.capture(SCREENSHOTS[self.index], now, 'next_initial')
            return False
        if self.phase == 'next_initial':
            self.index += 1
            if self.index == 2:
                self.index, self.step = 0, 2
                self.emit('p09d_scenario_relogin_verified', vehicles=2)
                self.transition('select_operation', now)
            else:
                self.transition('select_initial', now)
            return False
        vehicle, counts, name = OPERATIONS[self.index]
        if self.phase == 'select_operation':
            self.native.select(vehicle)
            self.transition('open_operation', now)
            return False
        if current['selected_inventory_id'] != vehicle or observed.get('vehicle_model_loaded') is not True:
            return False
        if self.phase in ('open_operation', 'open_result'):
            self.observe(vehicle)
            self.last_render = None
            self.native.open()
            self.transition('render_operation' if self.phase == 'open_operation' else 'render_result', now)
            return False
        if self.phase in ('render_operation', 'render_result'):
            if not self.rendered(vehicle):
                return False
            basename = 'p09d_' + name if self.phase == 'render_operation' else 'p09d_' + ('ms1' if vehicle == 1 else 'is7') + ('_restored' if self.index >= 4 else '_result')
            self.capture(basename, now, 'submit' if self.phase == 'render_operation' else 'close_result')
            return False
        if self.phase == 'submit':
            self.observe(vehicle)
            depot = [spare + old - new for spare, old, new in zip(self.depots[vehicle - 1], self.counts[vehicle - 1], counts)]
            self.pending = {'vehicle':vehicle, 'counts':list(counts), 'depot':depot, 'request':False, 'update':False,
                            'response':None, 'processor':False, 'complete':False}
            self.emit('p09d_scenario_action', callback='TechnicalMaintenance.fillVehicle', vehicle=vehicle,
                      counts=list(counts), no_purchase_branch=True, computer_input=False)
            self.transition('wait_service', now)
            self.native.fill(vehicle, counts)
            return False
        if self.phase == 'wait_service':
            if not self.pending['complete']:
                return False
            self.counts[vehicle - 1], self.depots[vehicle - 1] = list(counts), self.pending['depot']
            self.observe(vehicle)
            if self.native.window() is not None:
                return False
            self.results.append(copy.deepcopy(self.pending))
            self.emit('p09d_scenario_service_verified', result=self.pending)
            self.pending = None
            self.transition('open_result' if self.index in (1, 3, 4, 5) else 'next_operation', now)
            return False
        if self.phase == 'close_result':
            self.native.close()
            self.transition('next_operation', now)
            return False
        if self.phase == 'next_operation':
            if self.native.window() is not None:
                return False
            self.index += 1
            if self.index == len(OPERATIONS):
                if self.counts != [list(v) for v in INITIAL] or self.depots != [v['depot'] for v in self.expected['initial']]:
                    raise RuntimeError('native service did not restore initial loads and depot')
                self.completed = True
                self.transition('complete', now)
                self.emit('p09d_scenario_complete', operations=6, steps=7, restored_initial_state=True, screenshots=len(self.screenshots),
                          computer_input=False, native_pixels_review='NOT_RUN', human_manual_acceptance='NOT_RUN')
                return True
            self.step += 1
            self.transition('select_operation', now)
        return False


def native_event(fields):
    if _scenario is not None:
        _scenario.native_event(fields)


def advance(record, settings, observed, ready_hangar):
    global _scenario
    if _expected is None:
        return False
    try:
        if _scenario is None:
            _scenario = _Scenario(settings, record)
        return _scenario.advance(observed, ready_hangar)
    except Exception as error:
        if _scenario is not None:
            _scenario.phase = 'error'
        record('p09d_scenario_error', version=VERSION, error_type=type(error).__name__, error=str(error))
        raise
