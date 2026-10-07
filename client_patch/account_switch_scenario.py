# -*- coding: utf-8 -*-
"""Explicit original #717 primary/alternate/primary diagnostic, no input events.

Imports are engine-free. The original relogin action bindings and screenshot
reader are reused without changing their source or resetting any native cache.
Only the opt-in caller may arm this module and quit after its observed result.
"""
import hashlib
import json
import math
import re

from hangar_relogin_scenario import _Native as ReloginNative
from hangar_relogin_scenario import checked_login_state, disconnected_login
from ms1_crew_scenario import _integer, _now, integer_types, string_types

VERSION = 1
MAX_ADVANCES = 900
STABLE_SECONDS = 15.0
HOLD_SECONDS = 16.0
MAX_SAMPLE_GAP = 2.5
MAX_EXPECTED_BYTES = 6144
MAX_SNAPSHOT_BYTES = 16384
SCREENSHOTS = ('switch_primary_first', 'switch_secondary', 'switch_primary_return')
ACCOUNT_INDICES = (0, 1, 0)
_credentials = None
_expected_accounts = None
_armed = False
_scenario = None


class LoginRejected(RuntimeError):
    """An original expected login rejection, handled outside its callback."""


def _text(value, maximum):
    if type(value) is bytes:
        value = value.decode('utf-8', 'strict')
    if type(value) not in string_types or not 1 <= len(value) <= maximum:
        raise ValueError('bounded native text required')
    value.encode('utf-8', 'strict')
    return value


def _hash(value):
    if type(value) not in string_types or re.match(r'\A[0-9a-f]{64}\Z', value) is None:
        raise ValueError('exact SHA256 required')
    return value


def _keys(value, keys):
    if type(value) is not dict or set(value) != set(keys):
        raise ValueError('exact bounded account snapshot fields required')


def _encoded(value, maximum):
    raw = json.dumps(value, ensure_ascii=True, sort_keys=True,
                     separators=(',', ':'), allow_nan=False).encode('ascii')
    if len(raw) > maximum:
        raise ValueError('account snapshot byte budget exceeded')
    return raw


def checked_snapshot(value):
    """Validate primitive actual/expected data, never supply missing inventory."""
    _keys(value, ('database_id', 'name', 'resources', 'statistics', 'vehicles',
                  'tankmen', 'account_dossier_sha256'))
    _integer(value['database_id'], 1, 2147483647)
    name = _text(value['name'], 128)
    _hash(value['account_dossier_sha256'])
    for field, names in (('resources', ('credits', 'gold', 'free_xp')),
                         ('statistics', ('battles', 'wins', 'losses', 'draws'))):
        _keys(value[field], names)
        for number in value[field].values():
            _integer(number, 0, 9223372036854775807)
    vehicles, tankmen = value['vehicles'], value['tankmen']
    if (type(vehicles) is not list or not 1 <= len(vehicles) <= 8
            or type(tankmen) is not list or len(tankmen) > 16):
        raise ValueError('bounded native owned fleet and crew required')
    vehicle_ids, assignments = [], {}
    for vehicle in vehicles:
        _keys(vehicle, ('inventory_id', 'type_compact_descr', 'compact_descr_sha256', 'health', 'crew_ids'))
        identity = _integer(vehicle['inventory_id'], 1, 2147483647)
        vehicle_ids.append(identity)
        _integer(vehicle['type_compact_descr'], 1, 2147483647)
        _integer(vehicle['health'], 0, 100000)
        _hash(vehicle['compact_descr_sha256'])
        crew = vehicle['crew_ids']
        if type(crew) is not list or not 1 <= len(crew) <= 8:
            raise ValueError('bounded actual vehicle crew slots required')
        for slot, tankman in enumerate(crew):
            if tankman is None:
                continue
            _integer(tankman, 1, 2147483647)
            if tankman in assignments:
                raise ValueError('tankman assigned to multiple native slots')
            assignments[tankman] = (identity, slot)
    if vehicle_ids != sorted(set(vehicle_ids)):
        raise ValueError('owned vehicle identities must be unique and sorted')
    tankman_ids, owners = [], {}
    for tankman in tankmen:
        _keys(tankman, ('inventory_id', 'compact_descr_sha256', 'vehicle_inventory_id', 'vehicle_slot_index'))
        identity = _integer(tankman['inventory_id'], 1, 2147483647)
        tankman_ids.append(identity)
        _hash(tankman['compact_descr_sha256'])
        vehicle = _integer(tankman['vehicle_inventory_id'], -1, 2147483647)
        slot = _integer(tankman['vehicle_slot_index'], -1, 7)
        if vehicle > 0:
            if slot < 0 or vehicle not in vehicle_ids:
                raise ValueError('tankman references absent native vehicle/slot')
            owners[identity] = (vehicle, slot)
        elif vehicle != -1 or slot != -1:
            raise ValueError('unassigned tankman metadata contradicts assignment')
    if tankman_ids != sorted(set(tankman_ids)) or assignments != owners:
        raise ValueError('owned crew and vehicle assignments must match both ways')
    result = dict(value)
    result['name'] = name
    # Serialize only after exact keys, counts, scalar types and ranges were checked.
    return json.loads(_encoded(result, MAX_SNAPSHOT_BYTES).decode('ascii'))


def checked_expected_accounts(value):
    """Public pure preflight shared by explicit control and the native arm."""
    if type(value) is not list or len(value) != 2:
        raise ValueError('exact primary and alternate expectations required')
    result = [checked_snapshot(row) for row in value]
    if (result[0]['database_id'] == result[1]['database_id']
            or result[0]['name'] == result[1]['name']):
        raise ValueError('account switch needs two distinct native identities')
    for account in result:
        first = account['vehicles'][0]
        if first['inventory_id'] != 1 or first['type_compact_descr'] != 3329:
            raise ValueError('this diagnostic requires each existing MS-1 inventory ID1')
    _encoded(result, MAX_EXPECTED_BYTES)
    return result


def arm(primary_credentials, alternate_credentials, expected_accounts):
    """Keep only the explicit alternate/primary submit queue in memory."""
    global _armed, _credentials, _expected_accounts
    import project_auth
    if _armed or _scenario is not None or _credentials is not None:
        clear_credentials()
        raise RuntimeError('account switch can be armed only once per process')
    try:
        pairs = []
        for value in (primary_credentials, alternate_credentials):
            _keys(value, ('username', 'password'))
            user, password = value['username'], value['password']
            if (type(user) not in string_types or type(password) not in string_types
                    or len(user) > 1024 or len(password) > 1024
                    or not project_auth.valid_email(user) or not project_auth.valid_password(password)):
                raise ValueError('explicit valid project credentials required')
            pairs.append((user, password))
        if project_auth.canonical_email(pairs[0][0]) == project_auth.canonical_email(pairs[1][0]):
            raise ValueError('two distinct project login identities required')
        expected = checked_expected_accounts(expected_accounts)
        _credentials, _expected_accounts = [pairs[1], pairs[0]], expected
        _armed = True
    except Exception:
        clear_credentials()
        raise


def clear_credentials():
    """Drop retained references; immutable Python strings cannot be zeroed."""
    global _credentials
    _credentials = None


def _take_credentials():
    if not _armed or type(_credentials) is not list or not _credentials:
        raise RuntimeError('explicit queued account credentials unavailable')
    return _credentials.pop(0)


def note_login_result(stage, status):
    """Passive bounded sink after the original watcher; never raise or act."""
    scenario = _scenario
    if (not _armed or scenario is None or scenario.phase != 'waiting_hangar'
            or scenario.session_index not in (2, 3) or not scenario.awaiting_login
            or scenario.pending_login_result is not None):
        return False
    if (type(stage) is not int or stage != 1 or type(status) not in string_types
            or not 1 <= len(status) <= 128
            or any(not ('A' <= char <= 'Z' or '0' <= char <= '9' or char == '_') for char in status)):
        return False
    scenario.pending_login_result = {'stage': stage, 'status': status}
    scenario.awaiting_login = False
    return True


def checked_state(value):
    _keys(value, ('account', 'selected_inventory_id', 'hangar_owner', 'crew_owner'))
    account = checked_snapshot(value['account'])
    selected = _integer(value['selected_inventory_id'], 1, 2147483647)
    if selected not in [v['inventory_id'] for v in account['vehicles']]:
        raise ValueError('selected vehicle is not in this native owned fleet')
    for key in ('hangar_owner', 'crew_owner'):
        _integer(value[key], 1, 18446744073709551615)
    result = dict(value)
    result['account'] = account
    return result


def _inventory_compacts(value, maximum, require_vehicle=False):
    if not isinstance(value, dict) or len(value) > 32:
        raise ValueError('bounded native inventory columns required')
    # Original empty tankman inventory legitimately has no compDescr column.
    raw = value.get('compDescr', {})
    if (not isinstance(raw, dict) or len(raw) > maximum
            or require_vehicle and not raw):
        raise ValueError('bounded native inventory compact descriptors required')
    for identity, compact in raw.items():
        _integer(identity, 1, 2147483647)
        if type(compact) is not bytes or not 1 <= len(compact) <= 4096:
            raise ValueError('native compact descriptor bytes required')
    return raw


class _Native(ReloginNative):
    def state(self):
        import BigWorld
        from CurrentVehicle import g_currentVehicle
        from gui.shared import g_itemsCache
        from ms1_crew_probe import _observed_vehicle, _observed_tankman
        context = self.context()  # Original ready Hangar/Crew/Carousel; releases GUI references.
        player = BigWorld.player()
        if player is None or player.databaseID != context['database_id']:
            raise RuntimeError('native Account changed before inventory observation')
        items = g_itemsCache.items
        vehicle_raw = _inventory_compacts(items.inventory.getCacheValue(1, {}), 8, True)
        tankman_raw = _inventory_compacts(items.inventory.getCacheValue(8, {}), 16)
        vehicles = []
        for identity in sorted(vehicle_raw):
            item = items.getVehicle(identity)
            row = _observed_vehicle(item)
            if (row['inventory_id'] != identity
                    or row['descriptor_sha256'] != hashlib.sha256(vehicle_raw[identity]).hexdigest()):
                raise ValueError('native vehicle getter/raw compact identity differs')
            vehicles.append({'inventory_id': identity, 'type_compact_descr': row['type_compact_descr'],
                             'compact_descr_sha256': row['descriptor_sha256'],
                             'health': _integer(item.health, 0, 100000),
                             'crew_ids': [slot['tankman_inventory_id'] for slot in row['crew']]})
        actual = items.getTankmen()
        if not isinstance(actual, dict) or len(actual) > 16 or set(actual) != set(tankman_raw):
            raise ValueError('native tankmen getter/raw inventory identities differ')
        tankmen = []
        for identity in sorted(actual):
            row = _observed_tankman(actual[identity])
            if (row['inventory_id'] != identity
                    or row['compact_descr_sha256'] != hashlib.sha256(tankman_raw[identity]).hexdigest()):
                raise ValueError('native tankman getter/raw compact identity differs')
            tankmen.append(dict((key, row[key]) for key in (
                'inventory_id', 'compact_descr_sha256', 'vehicle_inventory_id', 'vehicle_slot_index')))
        dossier = items.stats.accountDossier
        if type(dossier) is not bytes or len(dossier) > 65536:
            raise ValueError('bounded original account dossier bytes required')
        account = {'database_id': context['database_id'], 'name': _text(player.name, 128),
                   'resources': dict(zip(('credits', 'gold', 'free_xp'), context['resources'])),
                   'statistics': dict(zip(('battles', 'wins', 'losses', 'draws'), context['statistics'])),
                   'vehicles': vehicles, 'tankmen': tankmen,
                   'account_dossier_sha256': hashlib.sha256(dossier).hexdigest()}
        if (BigWorld.player() is not player or player.databaseID != account['database_id']
                or g_currentVehicle.invID != context['selected_inventory_id'] or not g_itemsCache.isSynced()):
            raise RuntimeError('native Account/selection/cache changed during observation')
        return checked_state({'account': account, 'selected_inventory_id': context['selected_inventory_id'],
                              'hangar_owner': context['hangar_owner'], 'crew_owner': context['crew_owner']})

    def request(self, basename):
        import BigWorld
        if basename not in SCREENSHOTS or basename in self.requested:
            raise ValueError('unsupported or repeated account-switch screenshot')
        if any(name.startswith(basename + '_') for name in self._entries()):
            raise ValueError('account-switch screenshot already exists')
        self.requested.add(basename)
        BigWorld.screenShot('png', basename)


class _Scenario(object):
    def __init__(self, settings, record, native=None, clock=None):
        if not callable(record) or not _armed or _credentials is None or _expected_accounts is None:
            raise RuntimeError('explicit account-switch arm and recorder required')
        self.native = _Native(settings) if native is None else native
        self.record, self.clock = record, _now if clock is None else clock
        self.expected = checked_expected_accounts(_expected_accounts)
        self.phase, self.session_index, self.advances = 'waiting_hangar', 1, 0
        self.last_time, self.ready_since, self.last_ready = None, None, None
        self.ready_samples, self.max_gap = 0, 0.0
        self.awaiting_login, self.pending_login_result, self.login_accepted = False, None, True
        self.completed, self.snapshots, self.intervals, self.screenshots = False, [], [], []
        self.emit('account_switch_start', expected_accounts=self.expected,
                  account_indices=list(ACCOUNT_INDICES), screenshot_basenames=list(SCREENSHOTS),
                  required_stable_seconds=STABLE_SECONDS, hold_seconds=HOLD_SECONDS,
                  max_sample_gap=MAX_SAMPLE_GAP, expected_snapshots=3,
                  computer_input=False, automatic_quit=False,
                  native_pixels_review='NOT_RUN', human_manual_acceptance='NOT_RUN')

    def emit(self, event, **fields):
        fields.update(version=VERSION, phase=self.phase, session_index=self.session_index)
        self.record(event, **fields)

    def state(self):
        actual = checked_state(self.native.state())
        if actual['account'] != self.expected[ACCOUNT_INDICES[self.session_index - 1]]:
            raise RuntimeError('actual native Account inventory/crew/dossier differs from its expected identity')
        return actual

    def reset_interval(self, reason):
        if self.ready_since is not None:
            self.emit('account_switch_interval_reset', reason=reason, began_at=self.ready_since,
                      last_ready_at=self.last_ready, samples=self.ready_samples)
        self.ready_since, self.last_ready, self.ready_samples, self.max_gap = None, None, 0, 0.0

    def ready_state(self, observed, ready_hangar):
        vehicle = observed.get('vehicle')
        if (ready_hangar is not True or observed.get('vehicle_model_loaded') is not True
                or type(observed.get('selected_inventory_id')) is not int
                or observed['selected_inventory_id'] != 1 or type(vehicle) is not dict
                or type(vehicle.get('type_compact_descr')) is not int or vehicle['type_compact_descr'] != 3329):
            return None
        state = self.state()
        return state if state['selected_inventory_id'] == 1 else None

    def advance(self, observed, ready_hangar):
        if self.completed:
            return True
        if self.phase == 'error':
            raise RuntimeError('failed account-switch diagnostic cannot resume')
        if self.pending_login_result is not None:
            result, self.pending_login_result = self.pending_login_result, None
            if result['status'] != 'LOGGED_ON':
                clear_credentials()
            self.emit('account_switch_login_result', stage=result['stage'], status=result['status'],
                      expected_session_index=self.session_index,
                      source='original_ConnectionManager.connectionWatcher',
                      callback_injected=False, handled_outside_callback=True)
            if result['status'] != 'LOGGED_ON':
                raise LoginRejected('original expected account-switch login was rejected')
            self.login_accepted = True
        self.advances += 1
        if self.advances > MAX_ADVANCES:
            raise RuntimeError('account-switch observation budget exhausted')
        now = self.clock()
        if (type(now) not in (int, float) or math.isnan(now) or math.isinf(now)
                or self.last_time is not None and now < self.last_time):
            raise ValueError('finite monotonic diagnostic clock required')
        self.last_time = now
        if type(ready_hangar) is not bool or type(observed) is not dict:
            raise TypeError('explicit original readiness observation required')
        if self.phase == 'waiting_hangar':
            if not self.login_accepted or not ready_hangar:
                return False
            current = self.state()
            if current['selected_inventory_id'] != 1:
                self.emit('account_switch_action', action='select_ms1', moment='call',
                          callback='TankCarousel.vehicleChange', inventory_id=1)
                self.native.select_ms1()
                self.emit('account_switch_action', action='select_ms1', moment='return', inventory_id=1)
            self.phase = 'stable_hangar'
            return False
        if self.phase == 'stable_hangar':
            current = self.ready_state(observed, ready_hangar)
            if current is None:
                self.reset_interval('not_ready')
                return False
            if self.last_ready is not None and now - self.last_ready > MAX_SAMPLE_GAP:
                self.reset_interval('sample_gap')
            if self.ready_since is None:
                self.ready_since = now
            if self.last_ready is not None:
                self.max_gap = max(self.max_gap, now - self.last_ready)
            self.last_ready, self.ready_samples = now, self.ready_samples + 1
            self.emit('account_switch_state', state=current, observed_at=now, began_at=self.ready_since,
                      stable_seconds=now - self.ready_since, samples=self.ready_samples, max_gap=self.max_gap)
            if now - self.ready_since < HOLD_SECONDS:
                return False
            self.intervals.append({'session_index': self.session_index, 'began_at': self.ready_since,
                                   'ended_at': now, 'seconds': now - self.ready_since,
                                   'samples': self.ready_samples, 'max_gap': self.max_gap})
            fingerprint = hashlib.sha256(_encoded(current['account'], MAX_SNAPSHOT_BYTES)).hexdigest()
            self.snapshots.append(fingerprint)
            self.emit('account_switch_snapshot', snapshot=current['account'], fingerprint=fingerprint,
                      observation_index=len(self.snapshots), inventory_mutation_requested=False,
                      selection_changed_by_observer=False)
            basename = SCREENSHOTS[self.session_index - 1]
            self.native.request(basename)
            self.emit('account_switch_screenshot_requested', basename=basename,
                      writer='BigWorld.screenShot', extension='png')
            self.phase = 'waiting_png'
            return False
        if self.phase == 'waiting_png':
            current = self.ready_state(observed, ready_hangar)
            if current is None:
                raise RuntimeError('native MS-1 lost readiness during account-switch screenshot')
            proof = self.native.screenshot(SCREENSHOTS[self.session_index - 1])
            if proof is None:
                return False
            self.screenshots.append(proof)
            self.emit('account_switch_screenshot', screenshot=proof, state=current)
            if self.session_index == 3:
                if self.snapshots[0] != self.snapshots[2] or self.snapshots[0] == self.snapshots[1]:
                    raise RuntimeError('native account-return snapshot isolation failed')
                clear_credentials()
                self.phase, self.completed = 'complete', True
                self.emit('account_switch_complete', screenshots=3, observations=len(self.snapshots),
                          snapshot_fingerprints=self.snapshots, intervals=self.intervals,
                          credential_references_cleared=True, computer_input=False, automatic_quit=False,
                          native_pixels_review='NOT_RUN', human_manual_acceptance='NOT_RUN')
                return True
            self.phase = 'waiting_disconnect'
            self.emit('account_switch_action', action='logoff', moment='call',
                      callback='AppEntry.logoff', decorated=True, disconnect_now=False)
            self.native.logoff()
            self.emit('account_switch_action', action='logoff', moment='return',
                      callback='AppEntry.logoff', actual_disconnect_proven=False)
            return False
        if self.phase == 'waiting_disconnect':
            state = checked_login_state(self.native.login_state())
            self.emit('account_switch_login_state', state=state, observed_at=now)
            if not disconnected_login(state):
                return False
            self.emit('account_switch_disconnected', state=state, observed_at=now,
                      next_session_index=self.session_index + 1,
                      watcher_or_lifecycle_invoked=False, repository_changed_by_scenario=False)
            username, password = _take_credentials()
            self.session_index, self.phase = self.session_index + 1, 'waiting_hangar'
            self.login_accepted = False
            self.reset_interval('next_session')
            try:
                self.emit('account_switch_action', action='login', moment='call',
                          callback='original_LoginView.onLogin', project_input_boundary=True,
                          submitted_credential_references_cleared=True, remaining_credential_pairs=len(_credentials))
                self.awaiting_login = True
                self.native.submit(username, password)
            finally:
                del username, password
            self.emit('account_switch_action', action='login', moment='return',
                      callback='original_LoginView.onLogin', submitted_credential_references_cleared=True,
                      remaining_credential_pairs=len(_credentials))
            return False
        raise RuntimeError('unsupported account-switch diagnostic phase')


def advance(record, settings, observed, ready_hangar):
    """Passive while unarmed; otherwise complete only after all three real legs."""
    global _scenario
    if not _armed and _scenario is None:
        return False
    try:
        if _scenario is None:
            _scenario = _Scenario(settings, record)
        return _scenario.advance(observed, ready_hangar)
    except Exception as error:
        clear_credentials()
        if _scenario is not None:
            _scenario.phase, _scenario.awaiting_login, _scenario.pending_login_result = 'error', False, None
            _scenario.native.release_context()
            _scenario.emit('account_switch_error', error_type=type(error).__name__, credential_references_cleared=True)
        else:
            record('account_switch_error', version=VERSION, phase='error', session_index=1,
                   error_type=type(error).__name__, credential_references_cleared=True)
        raise
