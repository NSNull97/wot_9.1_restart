# -*- coding: utf-8 -*-
"""One opt-in native cell/geometry checkpoint, deliberately without a Vehicle.

Only arm() initializes the three audited original services. Notes never raise
into native/profile callbacks. No Entity, world callback or geometry is created
here; the server and engine perform those operations independently.
"""
import arena_entry_probe as probe
import arena_bootstrap

VERSION = 1
MAX_ADVANCES = 239                 # arm reads once; probe's total bound is240
MAX_PENDING_NOTES = 32
MAX_TOTAL_NOTES = 64
AVATAR_ID = 0x09100002
VEHICLE_ID = 0x09100003
SPACE_ID = 1
CALLBACKS = {'onEnterWorld': (388, 316), 'onSpaceLoaded': (535, 33)}
GAME_METHODS = (
    ('onGeometryMapped', 'onGeometryMapped', 370, 2,
     '6c0ed01ffef2aec2656b8bf60636ac1cf32da3f7fe9221d37845db1b4f5391e6'),
    ('onChangeEnvironments', 'onChangeEnvironments', 337, 1,
     'a98de623dd80e80e740e673f13a289f4bda560c5ba814ee022bd6ecf9d90e6f2'),
)
_run = None
_arm_attempted = False
_closing = False
_finished_cleanup = False
_cleanup_errors = []


def _emit(record, event, **fields):
    fields['version'] = VERSION
    return probe._emit(record, event, fields)


def _small_int(value, low=0, high=0x7fffffffffffffff):
    return type(value) in probe.integer_types and low <= value <= high


class _Native(object):
    def __init__(self, record):
        self.record = record

    def account(self):
        import Account
        import BigWorld
        observation = probe.observe(self.record)
        identity = probe._account_identity(BigWorld.player(), Account.PlayerAccount)
        if (observation['player_owner_id'] != id(BigWorld.player()) or
                observation['entity_id'] != identity['entity_id']):
            raise RuntimeError('native Account changed during arena arm')
        return observation, identity

    def initialize(self):
        import game
        for contract in GAME_METHODS:
            probe._code_contract(getattr(game, contract[0]), contract, 'scripts/client/game.py')
        arena_bootstrap.init(self.record)

    def observe(self):
        return probe.observe(self.record)


class _Scenario(object):
    def __init__(self, record, native):
        self.record, self.native = record, native
        self.advances, self.sequence = 0, 0
        self.notes, self.open_calls, self.completed_calls = [], {}, []
        self.seen_call_ids = set()
        self.geometry = None
        self.avatar_owner = None
        self.note_error = None
        self.active, self.complete = False, False
        observation, identity = native.account()
        if (observation['player_is_original_account'] is not True or
                observation['native_connected'] is not True or
                observation['repository_present'] is not True or
                not _small_int(observation['repository_owner_id'], 1) or
                observation['entity_id'] != identity['entity_id'] or observation['name'] != identity['name']):
            raise RuntimeError('arena arm requires the actual connected original Account/repository')
        self.account = dict(identity)
        self.repository_owner = observation['repository_owner_id']
        native.initialize()
        self.active = True
        _emit(record, 'arena_space_armed', account=self.account,
              repository_owner_id=self.repository_owner, max_advances=MAX_ADVANCES,
              expected_avatar_id=AVATAR_ID, expected_space_id=SPACE_ID,
              expected_vehicle_id=VEHICLE_ID, expected_geometry=probe.GEOMETRY_PATH,
              services='original_decal_edge_triggers', native_entity_created_by_scenario=False)

    def _fail_note(self, reason):
        if self.note_error is None:
            self.note_error = reason
        return False

    def _queue(self, value):
        if len(self.notes) >= MAX_PENDING_NOTES or self.sequence >= MAX_TOTAL_NOTES:
            return self._fail_note('native callback note budget exhausted')
        self.sequence += 1
        value['sequence'] = self.sequence
        self.notes.append(value)
        return True

    def note_avatar(self, phase, method, source_line, offset, call_id, owner_id, entity_id, space_id):
        if not self.active:
            return False
        if type(method) not in probe.string_types or method not in CALLBACKS:
            return False
        if (type(phase) not in probe.string_types or phase not in ('call', 'return') or
                not _small_int(source_line, 1, 100000) or not _small_int(offset, -1, 100000) or
                not _small_int(call_id, 1) or not _small_int(owner_id, 1) or
                not _small_int(entity_id, 1, 2147483647) or
                (space_id is not None and not _small_int(space_id, 0, 4294967295))):
            return self._fail_note('invalid primitive Avatar callback note')
        return self._queue(dict(kind='avatar', phase=phase, method=method, source_line=source_line,
                               offset=offset, call_id=call_id, owner_id=owner_id,
                               entity_id=entity_id, space_id=space_id))

    def note_geometry(self, space_id, path):
        if not self.active:
            return False
        if (not _small_int(space_id, 1, 4294967295) or
                type(path) not in probe.string_types or len(path) > 128):
            return self._fail_note('invalid primitive geometry callback note')
        try:
            path = probe._text(path, 128, 'geometry path')
        except (ValueError, UnicodeError):
            return self._fail_note('invalid native geometry path text')
        return self._queue(dict(kind='geometry', space_id=space_id, path=path))

    def _drain(self):
        if self.note_error is not None:
            raise RuntimeError(self.note_error)
        pending, self.notes = self.notes, []
        for note in pending:
            fields = dict(note)
            del fields['kind']
            if note['kind'] == 'geometry':
                _emit(self.record, 'arena_space_geometry', **fields)
                if (self.geometry is not None or note['space_id'] != SPACE_ID or
                        note['path'] != probe.GEOMETRY_PATH):
                    raise RuntimeError('unexpected duplicate/foreign native geometry mapping')
                self.geometry = note
                continue
            _emit(self.record, 'arena_space_callback', **fields)
            line, normal_return = CALLBACKS[note['method']]
            if (note['source_line'] != line or note['entity_id'] != AVATAR_ID or
                    note['offset'] != (-1 if note['phase'] == 'call' else normal_return)):
                raise RuntimeError('original Avatar callback contract did not complete normally')
            if note['phase'] == 'call':
                if note['call_id'] in self.seen_call_ids:
                    raise RuntimeError('duplicate original callback call ID')
                self.seen_call_ids.add(note['call_id'])
                self.open_calls[note['call_id']] = note
            else:
                entry = self.open_calls.pop(note['call_id'], None)
                if entry is None or any(entry[key] != note[key] for key in
                                        ('method', 'source_line', 'owner_id', 'entity_id', 'space_id')):
                    raise RuntimeError('original Avatar callback return has no matching entry')
                self.completed_calls.append({'entry': entry, 'returned': note})

    def advance(self):
        if self.complete:
            return True
        if not self.active:
            raise RuntimeError('arena space scenario is no longer active')
        self.advances += 1
        if self.advances > MAX_ADVANCES:
            raise RuntimeError('arena space observation budget exhausted')
        self._drain()
        value = self.native.observe()
        _emit(self.record, 'arena_space_state', advance=self.advances, observation=value,
              geometry_note_present=self.geometry is not None,
              callback_pairs=len(self.completed_calls))
        if (value['native_connected'] is not True or value['repository_present'] is not True or
                value['repository_owner_id'] != self.repository_owner):
            raise RuntimeError('original native session/repository changed during arena transition')
        if value['player_is_original_account']:
            if self.avatar_owner is not None or any(value[key] != self.account[key] for key in ('entity_id', 'name')):
                raise RuntimeError('unexpected Account replacement during arena transition')
            return False
        if not value['player_present']:
            return False
        if value['player_is_original_avatar'] is not True:
            raise RuntimeError('unexpected original player class during arena transition')
        if (value['entity_id'] != AVATAR_ID or value['name'] != self.account['name'] or
                (self.avatar_owner is not None and value['player_owner_id'] != self.avatar_owner)):
            raise RuntimeError('native Avatar identity changed')
        self.avatar_owner = value['player_owner_id']
        if value['space_id'] not in (None, SPACE_ID):
            raise RuntimeError('unexpected native space ID')
        if value['player_vehicle_id'] not in (None, 0, VEHICLE_ID):
            raise RuntimeError('unexpected future own Vehicle ID')
        if value['vehicle_present'] is not False:
            raise RuntimeError('this checkpoint does not create a Vehicle')
        if value['user_sees_world'] is True or value['steps_till_init'] == 0:
            raise RuntimeError('no-Vehicle checkpoint unexpectedly reports full world readiness')
        if value['arena_present'] and (value['arena_type_id'] != 1 or value['arena_unique_id'] != 1 or
                value['geometry_path'] != probe.GEOMETRY_PATH or value['geometry_name'] != probe.GEOMETRY_NAME):
            raise RuntimeError('native ClientArena differs from the explicit local map')
        qualified = {}
        for pair in self.completed_calls:
            row = pair['returned']
            if row['owner_id'] != self.avatar_owner:
                raise RuntimeError('original callback belongs to another Avatar owner')
            if row['space_id'] != SPACE_ID:
                continue
            if row['method'] == 'onSpaceLoaded' and (self.geometry is None or
                    pair['entry']['sequence'] <= self.geometry['sequence']):
                continue
            if row['method'] in qualified:
                raise RuntimeError('duplicate qualified original space callback')
            qualified[row['method']] = pair
        ready = bool(self.geometry is not None and set(qualified) == set(CALLBACKS) and
            not self.open_calls and value['in_world'] is True and value['space_id'] == SPACE_ID and
            value['arena_present'] is True and value['space_load_progress'] == 1.0 and
            value['position'] is not None and value['player_vehicle_id'] == VEHICLE_ID and
            _small_int(value['steps_till_init'], 1, 4) and value['user_sees_world'] is False)
        if not ready:
            return False
        self.complete, self.active = True, False
        _emit(self.record, 'arena_space_complete', checkpoint='cell_and_space_without_vehicle',
              advance=self.advances, observation_index=value['observation_index'],
              avatar_owner_id=self.avatar_owner, repository_owner_id=self.repository_owner,
              original_callback_ids=dict((key, pair['returned']['call_id']) for key, pair in qualified.items()),
              geometry_sequence=self.geometry['sequence'], space_initialized_observed=value['space_initialized'],
              geometry_loaded=True, full_world_ready=False, battle_ready=False, compatibility_acceptance=False)
        return True


def arm(record):
    global _run, _arm_attempted
    if _arm_attempted or _closing:
        raise RuntimeError('arena space scenario already armed or closing')
    _arm_attempted = True
    _run = _Scenario(record, _Native(record))


def note_avatar_call(phase, method, source_line, offset, call_id, owner_id, entity_id, space_id):
    if _run is None or _closing:
        return False
    return _run.note_avatar(phase, method, source_line, offset, call_id, owner_id, entity_id, space_id)


def note_geometry_mapped(space_id, path):
    if _run is None or _closing:
        return False
    return _run.note_geometry(space_id, path)


def advance(record):
    if _run is None or _closing:
        return False
    try:
        return _run.advance()
    except Exception as error:
        _run.active = False
        _emit(record, 'arena_space_error', advance=_run.advances, error_type=type(error).__name__,
              completion=False, full_world_ready=False)
        raise


def fini(record, native_cleanup):
    """Attempt all three ordered phases; retain every failure until the end."""
    global _closing, _finished_cleanup
    if _finished_cleanup:
        if _cleanup_errors:
            raise RuntimeError('arena cleanup previously failed: ' + ', '.join(_cleanup_errors))
        return
    _closing = True
    for name, function in (('before_entities', arena_bootstrap.fini_before_entities),
                           ('native_hangar_cleanup', native_cleanup),
                           ('after_entities', arena_bootstrap.fini_after_entities)):
        failed = None
        try:
            function()
        except Exception as error:
            failed = type(error).__name__
            _cleanup_errors.append(name + ':' + failed)
        try:
            _emit(record, 'arena_space_cleanup', stage=name, outcome='FAIL' if failed else 'PASS',
                  error_type=failed)
        except Exception as error:
            _cleanup_errors.append(name + ':record:' + type(error).__name__)
    _finished_cleanup = True
    if _cleanup_errors:
        raise RuntimeError('arena cleanup failed: ' + ', '.join(_cleanup_errors))
