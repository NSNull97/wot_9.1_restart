# -*- coding: utf-8 -*-
"""Explicit #717 MS-1 ammunition observation, with no purchase/reload action.

Engine-free import and strict public expectations. The caller owns real login
and may quit only after the observed result or an explicit diagnostic failure.
The frozen Account getter and screenshot machinery is reused unchanged.
"""
import hashlib
import json
import math

from account_switch_scenario import _Native as AccountNative
from account_switch_scenario import checked_snapshot as checked_account
from account_switch_scenario import checked_state as checked_account_state
from account_switch_scenario import _keys, _hash, _encoded, MAX_SNAPSHOT_BYTES
from ms1_crew_scenario import _integer, _now, integer_types
import ms1_ammo_probe as probe

VERSION = 1
MAX_ADVANCES = 160
MAX_SAMPLE_GAP = 2.5
STABLE_SECONDS = 15.0
HOLD_SECONDS = 16.0
MIDDLE_SECONDS = 8.0
SCREENSHOTS = ('ammo_start', 'ammo_end')
COUNTS = (20, 0, 0)
_armed = False
_expected = None
_scenario = None


def checked_expected(value):
    """Pure host/native preflight; no credentials or native modules are read."""
    _keys(value, ('version', 'account', 'vehicle_inventory_id', 'vehicle_compact_descr_sha256',
                  'turret_compact_descr', 'gun_compact_descr', 'max_ammo', 'shells',
                  'auto_load', 'storage_shells'))
    _integer(value['version'], VERSION, VERSION)
    account = checked_account(value['account'])
    vehicles = account['vehicles']
    if (len(vehicles) != 2 or [(v['inventory_id'], v['type_compact_descr']) for v in vehicles]
            != [(1, 3329), (2, 7169)] or len(account['tankmen']) != 2
            or vehicles[0]['crew_ids'] != [1, 2] or vehicles[1]['crew_ids'] != [None] * 5):
        raise ValueError('the existing primary MS-1/IS-7 fleet and assigned crew are required')
    _integer(value['vehicle_inventory_id'], 1, 1)
    _hash(value['vehicle_compact_descr_sha256'])
    if value['vehicle_compact_descr_sha256'] != vehicles[0]['compact_descr_sha256']:
        raise ValueError('ammo expectation must reference the same actual MS-1 descriptor')
    _integer(value['turret_compact_descr'], 5891, 5891)
    _integer(value['gun_compact_descr'], 5892, 5892)
    _integer(value['max_ammo'], 96, 96)
    if value['auto_load'] is not False or type(value['storage_shells']) is not list or value['storage_shells']:
        raise ValueError('this grant has no auto-load and no additional spare-shell inventory')
    rows = value['shells']
    if type(rows) is not list or len(rows) != 3:
        raise ValueError('three measured MS-1 shell expectations required')
    for row, cd, count in zip(rows, probe.SHELL_CDS, COUNTS):
        _keys(row, ('compact_descr', 'count'))
        _integer(row['compact_descr'], cd, cd)
        _integer(row['count'], count, count)
    result = dict(value)
    result['account'] = account
    return json.loads(_encoded(result, 6144).decode('ascii'))


def arm(value):
    global _armed, _expected
    if _armed or _scenario is not None:
        raise RuntimeError('MS-1 ammo diagnostic may be armed only once per process')
    _expected, _armed = checked_expected(value), True


def checked_state(value):
    _keys(value, ('account_state', 'account_owner', 'ammunition_owner', 'ammunition_flash_bound'))
    state = checked_account_state(value['account_state'])
    for key in ('account_owner', 'ammunition_owner'):
        _integer(value[key], 1, 18446744073709551615)
    if value['ammunition_flash_bound'] is not True:
        raise ValueError('the actual original ammunition panel must be Flash-bound')
    result = dict(value)
    result['account_state'] = state
    return result


def checked_ammo(value, expected):
    """Check actual probe primitives independently of the legacy fullness flag."""
    required = ('version', 'type_name', 'type_id', 'vehicle_inventory_id',
                'vehicle_type_compact_descr', 'vehicle_compact_descr_sha256', 'turret', 'gun',
                'max_ammo', 'shell_item_type', 'shells', 'native_empty_ammo', 'native_default_ammo',
                'observation', 'selection_before', 'selection_after', 'selection_unchanged',
                'inventory_mutation_requested', 'loaded_module_files', 'observation_index')
    if (type(value) is not dict or set(value) not in (set(required), set(required) | set(('sources',)))):
        raise ValueError('bounded original ammo observation required')
    _integer(value.get('version'), 1, 1)
    _integer(value.get('observation_index'), 1, probe.MAX_OBSERVATIONS)
    for field, number in (('vehicle_inventory_id', 1), ('vehicle_type_compact_descr', 3329),
                          ('max_ammo', 96), ('shell_item_type', 10)):
        _integer(value[field], number, number)
    if (value.get('type_name') != 'ussr:MS-1' or value.get('type_id') != [0, 13]
            or value.get('vehicle_inventory_id') != 1 or value.get('vehicle_type_compact_descr') != 3329
            or value.get('vehicle_compact_descr_sha256') != expected['vehicle_compact_descr_sha256']
            or value.get('max_ammo') != 96 or value.get('shell_item_type') != 10
            or value.get('gun') != {'resource_name': '_37mm_Gochkins', 'compact_descr': 5892}
            or value.get('turret') != {'resource_name': 'T-18_Standart', 'compact_descr': 5891}
            or value.get('selection_unchanged') is not True
            or value.get('inventory_mutation_requested') is not False):
        raise ValueError('actual native MS-1 descriptor or read-only contract differs')
    selection = value.get('selection_before')
    _keys(selection, ('database_id', 'selected_inventory_id', 'selected_descriptor_sha256'))
    _integer(selection['database_id'], 1, 2147483647)
    _integer(selection['selected_inventory_id'], 1, 1)
    _hash(selection['selected_descriptor_sha256'])
    if (selection != value.get('selection_after')
            or selection['database_id'] != expected['account']['database_id']
            or selection['selected_inventory_id'] != 1
            or selection['selected_descriptor_sha256'] != expected['vehicle_compact_descr_sha256']):
        raise ValueError('actual ammo observation is not the selected owned MS-1')
    shell_rows = value.get('shells')
    if type(shell_rows) is not list or len(shell_rows) != 3:
        raise ValueError('actual ordered original shell descriptors required')
    for row, (name, item_id, compact, kind) in zip(shell_rows, probe.SHELLS):
        if type(row) is not dict or row.get('compatible_with_mounted_gun') is not True:
            raise ValueError('actual native compatibility boolean required')
        if row != {'resource_name': name, 'item_id': [0, item_id], 'compact_descr': compact,
                   'kind': kind, 'compatible_with_mounted_gun': True}:
            raise ValueError('actual shell descriptor or compatibility result differs')
    flat = [2570, 20, 2826, 0, 3082, 0]
    if (value.get('native_empty_ammo') != [2570, 0, 2826, 0, 3082, 0]
            or value.get('native_default_ammo') != [2570, 96, 2826, 0, 3082, 0]):
        raise ValueError('actual original empty/default gun ammo differs')
    observation = value.get('observation')
    _keys(observation, ('raw_shells', 'raw_layouts', 'layout_index', 'mounted_layout_present',
                       'storage_shells', 'gui_shells', 'native_loaded_pairs', 'native_layout_rows',
                       'ammo_sum', 'default_ammo_sum', 'ammo_max_size', 'is_ammo_full', 'is_auto_load'))
    if (probe.checked_flat(observation['raw_shells']) != flat
            or observation['raw_layouts'] != [{'layout_index': [5891, 5892], 'shells': flat}]
            or observation['layout_index'] != [5891, 5892]
            or observation['mounted_layout_present'] is not True
            or observation['storage_shells'] != [] or type(observation['storage_shells']) is not list
            or observation['native_loaded_pairs'] != [[2570, 20], [2826, 0], [3082, 0]]
            or observation['native_layout_rows'] != [[2570, 20, False], [2826, 0, False], [3082, 0, False]]
            or observation['is_auto_load'] is not False or observation['is_ammo_full'] is not True):
        raise ValueError('actual loaded/layout/storage/original iterator data differs from the grant')
    for key, required in (('ammo_sum', 20), ('default_ammo_sum', 20), ('ammo_max_size', 96)):
        _integer(observation[key], required, required)
    layouts = observation['raw_layouts']
    if type(layouts) is not list or len(layouts) != 1:
        raise ValueError('one original mounted layout required')
    _keys(layouts[0], ('layout_index', 'shells'))
    if probe.checked_flat(layouts[0]['shells']) != flat:
        raise ValueError('actual mounted layout counts or types differ')
    for field, expected_rows in (('native_loaded_pairs', [[2570, 20], [2826, 0], [3082, 0]]),
                                  ('native_layout_rows', [[2570, 20, False], [2826, 0, False], [3082, 0, False]])):
        rows = observation[field]
        if type(rows) is not list or len(rows) != 3:
            raise ValueError('bounded actual native iterator rows required')
        for row, numbers in zip(rows, expected_rows):
            if type(row) is not list or len(row) != len(numbers):
                raise ValueError('native iterator row shape differs')
            _integer(row[0], numbers[0], numbers[0])
            _integer(row[1], numbers[1], numbers[1])
            if len(row) == 3 and row[2] is not False:
                raise ValueError('native layout currency flag differs')
    gui = observation['gui_shells']
    if type(gui) is not list or len(gui) != 3:
        raise ValueError('three actual original GUI Shell getters required')
    for row, shell, count in zip(gui, probe.SHELLS, COUNTS):
        _keys(row, ('compact_descr', 'kind', 'count', 'default_count', 'is_bought_for_credits',
                    'default_layout_value', 'inventory_count', 'buy_price', 'default_price'))
        _integer(row['compact_descr'], shell[2], shell[2])
        _integer(row['count'], count, count)
        _integer(row['default_count'], count, count)
        _integer(row['inventory_count'], 0, 0)
        if (row['kind'] != shell[3] or row['is_bought_for_credits'] is not False
                or probe.checked_flat(row['default_layout_value']) != [shell[2], count]):
            raise ValueError('actual GUI shell layout/type differs')
        probe._price(row['buy_price'], 'observed buyPrice')
        probe._price(row['default_price'], 'observed defaultPrice')
    return json.loads(_encoded(observation, 6144).decode('ascii'))


class _Native(AccountNative):
    def state(self):
        import BigWorld
        from gui.WindowsManager import g_windowsManager
        from gui.Scaleform.framework import ViewTypes
        from gui.Scaleform.daapi.view.lobby.hangar.AmmunitionPanel import AmmunitionPanel
        current = AccountNative.state(self)
        page = g_windowsManager.window.containerManager.getContainer(ViewTypes.LOBBY_SUB).getView()
        panel = page.components.get('ammunitionPanel')
        player = BigWorld.player()
        if (id(page) != current['hangar_owner'] or type(panel) is not AmmunitionPanel
                or panel.flashObject is None or player is None or type(player).__name__ != 'PlayerAccount'
                or player.databaseID != current['account']['database_id']):
            raise RuntimeError('actual Account/Hangar/ammunition panel changed or is unbound')
        return checked_state({'account_state': current, 'account_owner': id(player),
                              'ammunition_owner': id(panel), 'ammunition_flash_bound': True})

    def ammo(self, record):
        return probe.observe(record)

    def request(self, basename):
        import BigWorld
        if basename not in SCREENSHOTS or basename in self.requested:
            raise ValueError('unsupported or repeated MS-1 ammo screenshot')
        if any(name.startswith(basename + '_') for name in self._entries()):
            raise ValueError('MS-1 ammo screenshot basename already exists')
        self.requested.add(basename)
        BigWorld.screenShot('png', basename)


class _Scenario(object):
    def __init__(self, settings, record, native=None, clock=None):
        if not _armed or _expected is None or not callable(record):
            raise RuntimeError('explicit ammo arm and recorder required')
        self.native = _Native(settings) if native is None else native
        self.clock, self.record = _now if clock is None else clock, record
        self.expected = checked_expected(_expected)
        self.phase, self.advances, self.completed = 'waiting_hangar', 0, False
        self.last_time, self.began_at, self.last_ready = None, None, None
        self.samples, self.max_gap, self.identity = 0, 0.0, None
        self.snapshots, self.screenshots, self.pending_png = [], [], None
        self.emit('ms1_ammo_start', expected=self.expected, required_stable_seconds=STABLE_SECONDS,
                  hold_seconds=HOLD_SECONDS, middle_seconds=MIDDLE_SECONDS, max_sample_gap=MAX_SAMPLE_GAP,
                  screenshot_basenames=list(SCREENSHOTS), expected_snapshots=3,
                  computer_input=False, inventory_mutation_requested=False, timed_exit=False,
                  native_pixels_review='NOT_RUN', human_manual_acceptance='NOT_RUN')

    def emit(self, event, **fields):
        fields.update(version=VERSION, phase=self.phase)
        self.record(event, **fields)

    def state(self):
        current = checked_state(self.native.state())
        if current['account_state']['account'] != self.expected['account']:
            raise RuntimeError('actual account identity/resources/fleet/crew/dossier changed')
        identity = (current['account_owner'], current['ammunition_owner'],
                    current['account_state']['hangar_owner'], current['account_state']['crew_owner'])
        if self.identity is None:
            self.identity = identity
        elif self.identity != identity:
            raise RuntimeError('actual native Account or original GUI owners changed during observation')
        return current

    def snapshot(self, moment, current, now):
        if moment != ('start', 'middle', 'end')[len(self.snapshots)]:
            raise RuntimeError('ammo snapshots must be start/middle/end exactly once')
        raw = self.native.ammo(self.record)
        ammo = checked_ammo(raw, self.expected)
        value = {'account': current['account_state']['account'], 'ammo': ammo}
        fingerprint = hashlib.sha256(_encoded(value, MAX_SNAPSHOT_BYTES)).hexdigest()
        if self.snapshots and fingerprint != self.snapshots[0]['fingerprint']:
            raise RuntimeError('actual account/ammo changed across stable snapshots')
        row = {'moment': moment, 'observed_at': now, 'fingerprint': fingerprint,
               'ammo_observation_index': raw['observation_index']}
        if self.snapshots and row['ammo_observation_index'] <= self.snapshots[-1]['ammo_observation_index']:
            raise RuntimeError('each snapshot needs a fresh bounded native observation')
        self.snapshots.append(row)
        self.emit('ms1_ammo_snapshot', snapshot=value, moment=moment, observed_at=now,
                  fingerprint=fingerprint, ammo_observation_index=raw['observation_index'],
                  inventory_mutation_requested=False, selection_changed_by_observer=False)

    def request(self, basename, now):
        if self.pending_png is not None:
            raise RuntimeError('prior native ammo screenshot has not completed')
        self.native.request(basename)
        self.pending_png = basename
        self.emit('ms1_ammo_screenshot_requested', basename=basename, observed_at=now,
                  writer='BigWorld.screenShot', extension='png')

    def read_png(self, current, now):
        if self.pending_png is None:
            return
        proof = self.native.screenshot(self.pending_png)
        if proof is None:
            return
        if (type(proof) is not dict or proof.get('basename') != self.pending_png
                or proof.get('png_container_valid') is not True):
            raise ValueError('actual bounded native PNG evidence required')
        self.screenshots.append(proof)
        self.emit('ms1_ammo_screenshot', screenshot=proof, state=current, observed_at=now)
        self.pending_png = None

    def advance(self, observed, ready_hangar):
        if self.completed:
            return True
        if self.phase == 'error':
            raise RuntimeError('failed ammo diagnostic cannot resume')
        self.advances += 1
        if self.advances > MAX_ADVANCES:
            raise RuntimeError('bounded native ammo observation budget exhausted')
        now = self.clock()
        if (type(now) not in (int, float) or not 0 <= now <= 1e9
                or math.isnan(now) or math.isinf(now)
                or self.last_time is not None and now < self.last_time):
            raise ValueError('finite monotonic observation clock required')
        self.last_time = now
        if type(observed) is not dict or type(ready_hangar) is not bool:
            raise ValueError('actual original readiness observation required')
        if self.phase == 'waiting_hangar':
            if not ready_hangar:
                return False
            current = self.state()
            if current['account_state']['selected_inventory_id'] != 1:
                self.emit('ms1_ammo_action', action='select_ms1', moment='call',
                          callback='TankCarousel.vehicleChange', inventory_id=1)
                self.native.select_ms1()
                self.emit('ms1_ammo_action', action='select_ms1', moment='return', inventory_id=1)
            self.phase = 'waiting_ms1'
            return False
        vehicle = observed.get('vehicle')
        ready = (ready_hangar and type(observed.get('selected_inventory_id')) in integer_types
                 and observed['selected_inventory_id'] == 1
                 and observed.get('vehicle_model_loaded') is True and type(vehicle) is dict
                 and type(vehicle.get('type_compact_descr')) in integer_types
                 and vehicle['type_compact_descr'] == 3329)
        if not ready:
            if self.phase == 'waiting_ms1':
                return False
            raise RuntimeError('native MS-1 lost continuous readiness during ammo proof')
        current = self.state()
        if current['account_state']['selected_inventory_id'] != 1:
            raise RuntimeError('actual selected vehicle differs from the ready MS-1 observation')
        if self.last_ready is not None:
            gap = now - self.last_ready
            if gap > MAX_SAMPLE_GAP:
                raise RuntimeError('native ammo ready observation gap exceeded')
            self.max_gap = max(self.max_gap, gap)
        if self.began_at is None:
            self.began_at = now
        self.phase = 'stable_hangar'
        self.last_ready, self.samples = now, self.samples + 1
        self.emit('ms1_ammo_state', state=current, observed_at=now, began_at=self.began_at,
                  stable_seconds=now - self.began_at, samples=self.samples, max_gap=self.max_gap)
        self.read_png(current, now)
        if not self.snapshots:
            self.snapshot('start', current, now)
            self.request(SCREENSHOTS[0], now)
            return False
        elapsed = now - self.began_at
        if len(self.snapshots) == 1 and elapsed >= MIDDLE_SECONDS:
            self.snapshot('middle', current, now)
        if len(self.snapshots) == 2 and elapsed >= HOLD_SECONDS:
            if self.pending_png is not None:
                raise RuntimeError('first native PNG has not completed within the stable interval')
            self.snapshot('end', current, now)
            self.request(SCREENSHOTS[1], now)
            return False
        if len(self.snapshots) == 3 and len(self.screenshots) == 2 and self.pending_png is None:
            self.phase, self.completed = 'complete', True
            self.emit('ms1_ammo_complete', screenshots=2, observations=3,
                      snapshot_fingerprints=[row['fingerprint'] for row in self.snapshots],
                      began_at=self.began_at, ended_at=now, stable_seconds=elapsed,
                      samples=self.samples, max_gap=self.max_gap,
                      computer_input=False, inventory_mutation_requested=False, timed_exit=False,
                      native_pixels_review='NOT_RUN', human_manual_acceptance='NOT_RUN')
            return True
        return False


def advance(record, settings, observed, ready_hangar):
    """Normal unarmed operation is inert; explicit failures stay failures."""
    global _scenario
    if not _armed and _scenario is None:
        return False
    try:
        if _scenario is None:
            _scenario = _Scenario(settings, record)
        return _scenario.advance(observed, ready_hangar)
    except Exception as error:
        if _scenario is None:
            record('ms1_ammo_error', version=VERSION, phase='error', error_type=type(error).__name__)
        else:
            _scenario.phase = 'error'
            _scenario.native.release_context()
            _scenario.emit('ms1_ammo_error', error_type=type(error).__name__)
        raise
