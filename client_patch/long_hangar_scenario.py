# -*- coding: utf-8 -*-
"""Opt-in single-Account longevity diagnostic; no input, traffic or timer quit.

The original handler's passive return notes are observations, never replacements
for its work. Imports are engine-free; normal, unarmed operation is inert.
"""
import hashlib
import math

from account_switch_scenario import _Native as AccountNative
from account_switch_scenario import checked_snapshot, checked_state, _encoded, MAX_SNAPSHOT_BYTES
from ms1_crew_scenario import _integer, _now, integer_types

VERSION = 1
MIN_STATS_RETURNS = 181
MIN_STATS_SPAN = 900.0
MIDDLE_SECONDS = 450.0
MAX_SAMPLE_GAP = 3.0
MAX_STATS_GAP = 15.0
MAX_ADVANCES = 1600
MAX_STARTUP_ADVANCES = 120
MAX_STATS_RETURNS = 320
MAX_PENDING_NOTES = 8
MAX_SCREENSHOT_WAIT = 15.0
SCREENSHOTS = ('long_hangar_start', 'long_hangar_end')
ACCOUNT_SOURCE = 'scripts/client/Account.py'
STATS_SOURCE_LINE = 679
STATS_RETURN_OFFSET = 16
_armed = False
_expected = None
_scenario = None
_notes = []
_note_error = None
_closed = False


def _number(value):
    return (type(value) in (int, float) and 0 <= value <= 1e9
            and not math.isnan(value) and not math.isinf(value))


def checked_expected_primary(value):
    """Pure, bounded public expectation; never supplies native inventory data."""
    result = checked_snapshot(value)
    first = result['vehicles'][0]
    if first['inventory_id'] != 1 or first['type_compact_descr'] != 3329:
        raise ValueError('long Hangar requires the existing inventory MS-1 ID1')
    return result


def arm(expected_primary):
    global _armed, _expected
    if _armed or _scenario is not None or _closed:
        raise RuntimeError('long Hangar may be armed only once per process')
    checked = checked_expected_primary(expected_primary)
    _expected, _armed = checked, True


def note_stats_return(owner_id, call_id, source_line, offset, now):
    """Queue bounded primitives; do not raise, retain frames, log or act here."""
    global _note_error
    if not _armed or _closed:
        return False
    if _note_error is not None:
        return False
    if (type(owner_id) not in integer_types or not 1 <= owner_id <= 18446744073709551615
            or type(call_id) not in integer_types or not 1 <= call_id <= 2147483647
            or type(source_line) not in integer_types or source_line != STATS_SOURCE_LINE
            or type(offset) not in integer_types or offset != STATS_RETURN_OFFSET
            or not _number(now)):
        _note_error = 'invalid_original_stats_return'
        return False
    if len(_notes) >= MAX_PENDING_NOTES:
        _note_error = 'pending_stats_note_budget_exhausted'
        return False
    _notes.append({'owner_id': owner_id, 'native_call_id': call_id, 'source_line': source_line,
                   'offset': offset, 'observed_at': now})
    return True


class _Native(AccountNative):
    def account_owner(self):
        import BigWorld
        player = BigWorld.player()
        if player is None or type(player).__name__ != 'PlayerAccount':
            raise RuntimeError('actual original PlayerAccount owner required')
        return id(player)

    def request(self, basename):
        import BigWorld
        if basename not in SCREENSHOTS or basename in self.requested:
            raise ValueError('unsupported or repeated long Hangar screenshot')
        if any(name.startswith(basename + '_') for name in self._entries()):
            raise ValueError('long Hangar screenshot basename already exists')
        self.requested.add(basename)
        BigWorld.screenShot('png', basename)


class _Scenario(object):
    def __init__(self, settings, record, native=None, clock=None):
        if not _armed or _expected is None or not callable(record):
            raise RuntimeError('explicit long Hangar arm and recorder required')
        self.native = _Native(settings) if native is None else native
        self.record, self.clock = record, _now if clock is None else clock
        self.expected = checked_expected_primary(_expected)
        self.phase, self.completed, self.advances = 'waiting_hangar', False, 0
        self.last_time, self.ready_since, self.last_ready = None, None, None
        self.samples, self.max_gap, self.select_requested = 0, 0.0, False
        self.owner, self.view_owners, self.fingerprint = None, None, None
        self.note_owner, self.last_note_id, self.last_note_at = None, None, None
        self.note_count, self.stats_count, self.first_stats, self.last_stats = 0, 0, None, None
        self.snapshots, self.screenshots, self.pending_png = [], [], None
        self.emit('long_hangar_start', expected_primary=self.expected,
                  minimum_stats_returns=MIN_STATS_RETURNS, minimum_stats_span=MIN_STATS_SPAN,
                  max_sample_gap=MAX_SAMPLE_GAP, max_stats_gap=MAX_STATS_GAP,
                  max_advances=MAX_ADVANCES, screenshot_basenames=list(SCREENSHOTS),
                  snapshot_moments=['start', 'middle', 'end'], computer_input=False,
                  automatic_quit=False, native_pixels_review='NOT_RUN', human_manual_acceptance='NOT_RUN')

    def emit(self, event, **fields):
        fields.update(version=VERSION, phase=self.phase)
        self.record(event, **fields)

    def state(self):
        owner = _integer(self.native.account_owner(), 1, 18446744073709551615)
        actual = checked_state(self.native.state())
        if self.native.account_owner() != owner or actual['account'] != self.expected:
            raise RuntimeError('native Account, public inventory, resources or dossier changed')
        if self.owner is not None and owner != self.owner:
            raise RuntimeError('original Account instance changed during long Hangar')
        if self.note_owner is not None and owner != self.note_owner:
            raise RuntimeError('stats returns belong to another original Account')
        return actual, owner

    def flush_notes(self, now):
        if _note_error is not None:
            raise RuntimeError(_note_error)
        pending = list(_notes)
        del _notes[:]
        for note in pending:
            if (self.note_count >= MAX_STATS_RETURNS or note['observed_at'] > now
                    or self.last_note_id is not None and note['native_call_id'] <= self.last_note_id
                    or self.last_note_at is not None and note['observed_at'] <= self.last_note_at):
                raise RuntimeError('stats note count, unique call order or native clock differs')
            if self.note_owner is None:
                self.note_owner = note['owner_id']
            if note['owner_id'] != self.note_owner or self.owner is not None and note['owner_id'] != self.owner:
                raise RuntimeError('stats return owner changed')
            self.note_count += 1
            self.last_note_id, self.last_note_at = note['native_call_id'], note['observed_at']
            eligible = self.ready_since is not None and note['observed_at'] >= self.ready_since
            if eligible:
                if self.last_stats is not None and note['observed_at'] - self.last_stats > MAX_STATS_GAP:
                    raise RuntimeError('original periodic stats progress gap exceeded')
                self.stats_count += 1
                if self.first_stats is None:
                    self.first_stats = note['observed_at']
                self.last_stats = note['observed_at']
            self.emit('long_hangar_stats_return', source=ACCOUNT_SOURCE, method='receiveServerStats',
                      original_normal_return=True, eligible=eligible, note_index=self.note_count,
                      stats_returns=self.stats_count, first_stats_at=self.first_stats,
                      last_stats_at=self.last_stats, stats_span=self.stats_span(), **note)

    def stats_span(self):
        return 0.0 if self.first_stats is None else self.last_stats - self.first_stats

    def snapshot(self, moment, state, now):
        index = len(self.snapshots)
        if index >= 3 or moment != ('start', 'middle', 'end')[index]:
            raise RuntimeError('long Hangar snapshot sequence differs')
        fingerprint = hashlib.sha256(_encoded(state['account'], MAX_SNAPSHOT_BYTES)).hexdigest()
        if self.fingerprint is None:
            self.fingerprint = fingerprint
        if fingerprint != self.fingerprint:
            raise RuntimeError('long Hangar account snapshot changed')
        self.snapshots.append(fingerprint)
        self.emit('long_hangar_snapshot', moment=moment, snapshot_index=index+1,
                  account_owner=self.owner, selected_inventory_id=state['selected_inventory_id'],
                  snapshot=state['account'], fingerprint=fingerprint, observed_at=now,
                  inventory_mutation_requested=False)

    def request_png(self, basename, now):
        if self.pending_png is not None:
            raise RuntimeError('previous native screenshot still pending')
        self.native.request(basename)
        self.pending_png = (basename, now)
        self.emit('long_hangar_screenshot_requested', basename=basename, observed_at=now,
                  account_owner=self.owner, writer='BigWorld.screenShot', pixel_acceptance='NOT_RUN')

    def poll_png(self, now):
        if self.pending_png is None:
            return
        basename, requested = self.pending_png
        proof = self.native.screenshot(basename)
        if proof is None:
            if now - requested > MAX_SCREENSHOT_WAIT:
                raise RuntimeError('native screenshot progress budget exhausted')
            return
        if (type(proof) is not dict or proof.get('basename') != basename
                or proof.get('png_container_valid') is not True
                or proof.get('native_pixels_review') != 'NOT_RUN'):
            raise ValueError('actual bounded native PNG container required')
        self.screenshots.append(proof)
        self.pending_png = None
        self.emit('long_hangar_screenshot', screenshot=proof, observed_at=now,
                  account_owner=self.owner, fingerprint=self.fingerprint)

    def ready_state(self, observed, ready_hangar):
        if (ready_hangar is not True or observed.get('selected_inventory_id') != 1
                or type(observed.get('vehicle')) is not dict
                or observed['vehicle'].get('type_compact_descr') != 3329):
            raise RuntimeError('continuous original MS-1 Hangar readiness lost')
        for key in ('native_connected', 'items_cache_synced', 'vehicle_model_loaded', 'app_initialized',
                    'gui_initialized', 'hangar_space_inited', 'hangar_space_loaded', 'interactive_movie_started'):
            if observed.get(key) is not True:
                raise RuntimeError('continuous original Hangar readiness flag lost')
        if (observed.get('waiting_visible') is not False or observed.get('hangar_space_loading') is not False
                or observed.get('vehicle_model_count') != 4 or observed.get('vehicle_models_visible') != [True]*4):
            raise RuntimeError('continuous original vehicle render readiness lost')
        state, owner = self.state()
        owners = (state['hangar_owner'], state['crew_owner'])
        if state['selected_inventory_id'] != 1 or self.view_owners is not None and owners != self.view_owners:
            raise RuntimeError('native selection or bound Hangar/Crew view changed')
        if observed.get('resources') != self.expected['resources'] or observed.get('statistics') != self.expected['statistics']:
            raise RuntimeError('passive native Hangar resources or statistics changed')
        return state, owner, owners

    def advance(self, observed, ready_hangar):
        if self.completed:
            return True
        if self.phase == 'error':
            raise RuntimeError('failed long Hangar diagnostic cannot resume')
        self.advances += 1
        if self.advances > MAX_ADVANCES:
            raise RuntimeError('long Hangar observation budget exhausted')
        now = self.clock()
        if not _number(now) or self.last_time is not None and now < self.last_time:
            raise ValueError('finite monotonic diagnostic clock required')
        self.last_time = now
        if type(observed) is not dict or type(ready_hangar) is not bool:
            raise TypeError('explicit original readiness observation required')
        self.flush_notes(now)
        if self.phase == 'waiting_hangar':
            if self.advances > MAX_STARTUP_ADVANCES:
                raise RuntimeError('initial native Hangar progress budget exhausted')
            if not ready_hangar:
                return False
            state, owner = self.state()
            if state['selected_inventory_id'] != 1:
                if self.select_requested:
                    raise RuntimeError('original MS-1 selection did not complete')
                self.select_requested = True
                self.emit('long_hangar_action', action='select_ms1', moment='call',
                          callback='TankCarousel.vehicleChange', inventory_id=1)
                self.native.select_ms1()
                self.emit('long_hangar_action', action='select_ms1', moment='return', inventory_id=1)
                return False
            state, owner, owners = self.ready_state(observed, ready_hangar)
            self.owner, self.view_owners = owner, owners
            self.phase, self.ready_since = 'holding', now
            self.snapshot('start', state, now)
            self.request_png(SCREENSHOTS[0], now)
        state, owner, owners = self.ready_state(observed, ready_hangar)
        if self.last_ready is not None:
            gap = now - self.last_ready
            if gap > MAX_SAMPLE_GAP:
                raise RuntimeError('continuous native observation gap exceeded')
            self.max_gap = max(self.max_gap, gap)
        self.last_ready, self.samples = now, self.samples + 1
        progress_at = self.last_stats if self.last_stats is not None else self.ready_since
        if now - progress_at > MAX_STATS_GAP:
            raise RuntimeError('original periodic server statistics stopped progressing')
        self.emit('long_hangar_state', observed_at=now, began_at=self.ready_since,
                  ready_seconds=now-self.ready_since, samples=self.samples, max_sample_gap=self.max_gap,
                  account_owner=owner, hangar_owner=owners[0], crew_owner=owners[1],
                  selected_inventory_id=1, fingerprint=self.fingerprint,
                  stats_returns=self.stats_count, first_stats_at=self.first_stats,
                  last_stats_at=self.last_stats, stats_span=self.stats_span())
        self.poll_png(now)
        if len(self.snapshots) == 1 and now-self.ready_since >= MIDDLE_SECONDS:
            self.snapshot('middle', state, now)
        if (self.phase == 'holding' and self.stats_count >= MIN_STATS_RETURNS
                and self.stats_span() >= MIN_STATS_SPAN):
            if len(self.snapshots) != 2 or len(self.screenshots) != 1 or self.pending_png is not None:
                raise RuntimeError('required midpoint or first native screenshot missing')
            self.snapshot('end', state, now)
            self.phase = 'waiting_end_png'
            self.request_png(SCREENSHOTS[1], now)
            return False
        if self.phase == 'waiting_end_png' and len(self.screenshots) == 2:
            if len(self.snapshots) != 3 or len(set(self.snapshots)) != 1:
                raise RuntimeError('three unchanged public account snapshots required')
            self.completed = True
            self.emit('long_hangar_complete', observed_at=now, account_owner=self.owner,
                      stats_returns=self.stats_count, first_stats_at=self.first_stats,
                      last_stats_at=self.last_stats, stats_span=self.stats_span(),
                      began_at=self.ready_since, ready_seconds=now-self.ready_since,
                      samples=self.samples, max_sample_gap=self.max_gap, snapshots=3, screenshots=2,
                      snapshot_fingerprints=list(self.snapshots), timed_exit=False,
                      native_pixels_review='NOT_RUN', human_manual_acceptance='NOT_RUN')
            return True
        return False


def advance(record, settings, observed, ready_hangar):
    """Return true only for measured completion; failures are raised here."""
    global _scenario, _closed
    if not _armed and _scenario is None:
        return False
    try:
        if _scenario is None:
            _scenario = _Scenario(settings, record)
        result = _scenario.advance(observed, ready_hangar)
        if result:
            _closed = True
            del _notes[:]
        return result
    except Exception as error:
        _closed = True
        del _notes[:]
        if _scenario is not None:
            _scenario.phase = 'error'
            _scenario.native.release_context()
            _scenario.emit('long_hangar_error', error_type=type(error).__name__,
                           stats_returns=_scenario.stats_count, compatibility_acceptance=False)
        else:
            record('long_hangar_error', version=VERSION, phase='error',
                   error_type=type(error).__name__, compatibility_acceptance=False)
        raise
