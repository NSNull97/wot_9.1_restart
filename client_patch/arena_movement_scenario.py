# -*- coding: utf-8 -*-
"""Explicit #717 movement/position diagnostic, never an implementation of physics.

The server chooses a bounded test-lab path. We invoke the audited original
moveVehicle method, observe separate entity/model/filter outputs and request two
native PNGs. No keyboard, clock, entity position or filter state is assigned.
"""
import hashlib
import os

import arena_bootstrap
import arena_entry_probe as probe
import arena_vehicle_scenario as vehicle
import arena_ready_scenario as ready
from ms1_crew_scenario import _Native as ScreenshotNative, _now

VERSION = 1
MAX_ADVANCES, MAX_GAP, MAX_PNG_ADVANCES = 239, 3.0, 15
MAX_MOVEMENT_PENDING, MAX_MOVEMENT_NOTES = 32, 64
MIN_BASELINE_SECONDS, MIN_HOLD_SECONDS = 2.0, 2.0
MAX_COMMAND_SECONDS = 8.0
ORIGIN = (-58.499908447265625, 33.770267486572266, -445.81304931640625)
TARGET = (ORIGIN[0], ORIGIN[1], ORIGIN[2] + 2.0)
# 2cm is far above f32 resolution here (~0.00003m), below a single 0.1m
# server step, and does not conceal the measured physics-adjusted output Y.
XZ_TOLERANCE = 0.02
SCREENSHOTS = ('arena_movement_before', 'arena_movement_after')
MOVE_METHOD = ('moveVehicle', 'moveVehicle', 2130, 3,
               '1fa74dc9bb83f2e8103aa1a146b9c174bb4bcae7b0a7280b993eef5f8ac2f826')
SOURCE_HASHES = ready.SOURCE_HASHES + (
    ('res/scripts/client/Avatar.pyc', 'c13cd58a4c5d766dfd3c5f47ae7be50c962aee6c7f8cf25b4341322381f21e0e'),
    ('res/scripts/client/AvatarInputHandler/__init__.pyc', '7c7794130e208068b53ed6617ee06c99d0d2c26803c37e6a14cd1d27064a64d2'),
    ('res/scripts/client/VehicleGunRotator.pyc', 'd0105237b62447fee170cbf17984fd48437115087d6af6bf44743cc0cf68576a'),
)
_run = _native = None
_arm_attempted = _closing = _finished_cleanup = False
_cleanup_errors = []


def _emit(record, event, **fields):
    fields['version'] = VERSION
    return probe._emit(record, event, fields)


def _sources():
    root, rows = os.path.realpath(os.getcwd()), []
    for relative, expected in SOURCE_HASHES:
        path = os.path.join(root, *relative.split('/'))
        if (not os.path.realpath(path).startswith(root + os.sep) or os.path.islink(path)
                or not os.path.isfile(path) or not 1 <= os.path.getsize(path) <= 1048576):
            raise ValueError('bounded original movement source required')
        with open(path, 'rb') as stream:
            raw = stream.read(1048577)
        if len(raw) > 1048576 or hashlib.sha256(raw).hexdigest() != expected:
            raise ValueError('original movement source differs: ' + relative)
        rows.append(dict(relative_path=relative, bytes=len(raw), sha256=expected))
    return rows


def _move_binding():
    import Avatar
    probe._code_contract(Avatar.PlayerAvatar.moveVehicle, MOVE_METHOD, 'scripts/client/Avatar.py')


class _Pixels(ScreenshotNative):
    def request(self, basename):
        import BigWorld
        if basename not in SCREENSHOTS or basename in self.requested:
            raise ValueError('unsupported or repeated movement screenshot')
        names = self._entries()
        if any(not any(name.startswith(prefix + '_') and name.endswith('.png')
                       for prefix in self.requested) for name in names):
            raise ValueError('movement screenshot directory contains an unowned file')
        if any(name.startswith(basename + '_') for name in names):
            raise ValueError('movement screenshot must not overwrite a file')
        self.requested.add(basename)
        BigWorld.screenShot('png', basename)


class _Native(vehicle._Native):
    def __init__(self, record, settings):
        vehicle.space._Native.__init__(self, record)
        self.pixels, self.light, self.light_module = _Pixels(settings), None, None

    def initialize(self):
        self.movement_sources = _sources()
        ready._bindings()
        _move_binding()
        vehicle._Native.initialize(self)
        from LightFx import LightManager
        if LightManager.g_instance is not None:
            raise RuntimeError('movement refuses an existing LightManager singleton')
        self.light_module = LightManager
        _emit(self.record, 'arena_movement_light', phase='init_begin')
        self.light = LightManager.LightManager()
        if not arena_bootstrap._exact_instance(self.light, LightManager.LightManager):
            raise RuntimeError('original LightManager exact class required')
        LightManager.g_instance = self.light
        self.light.start()
        _emit(self.record, 'arena_movement_light', phase='init_return', owner_id=id(self.light),
              enabled=probe._boolean(self.light.isEnabled(), 'LightManager.isEnabled'),
              enabled_assigned_by_diagnostic=False)

    def light_fini(self):
        if self.light is None:
            return
        ready._bindings()
        if self.light_module.g_instance is not self.light:
            raise RuntimeError('owned LightManager binding changed')
        _emit(self.record, 'arena_movement_light', phase='destroy_begin', owner_id=id(self.light))
        self.light.destroy()
        self.light_module.g_instance = None
        _emit(self.record, 'arena_movement_light', phase='destroy_return', owner_id=id(self.light))
        self.light = self.light_module = None

    def motion(self):
        import Avatar
        import BigWorld
        import Math
        import Vehicle
        player, current = BigWorld.player(), BigWorld.entity(vehicle.VEHICLE_ID)
        if type(player) is not Avatar.PlayerAvatar or current is None or not current.isStarted:
            return {'present': False}
        if type(current) is not Vehicle.Vehicle or current.model is None:
            raise RuntimeError('original started own Vehicle/model required')
        arena = player.arena
        speed = current.filter.speedInfo.value
        return dict(present=True, owner_id=id(player), vehicle_owner_id=id(current),
            period=probe._integer(arena.period, 0, 4, 'period'),
            period_end_time=probe._number(arena.periodEndTime, 0, 1e9, 'period end'),
            period_length=probe._number(arena.periodLength, 0, 3600, 'period length'),
            additional_info_is_none=arena.periodAdditionalInfo is None,
            server_time=probe._number(BigWorld.serverTime(), -1e9, 1e9, 'native serverTime'),
            native_time=probe._number(BigWorld.time(), 0, 1e10, 'native time'),
            is_on_arena=probe._boolean(player.isOnArena, 'Avatar.isOnArena'),
            gun_rotator_started=probe._boolean(player.gunRotator._VehicleGunRotator__isStarted, 'rotator started'),
            cruise_mode=probe._integer(player._PlayerAvatar__cruiseControlMode, -100, 100, 'cruise mode'),
            entity_position=probe._position(current.position, 'entity position'),
            entity_matrix_position=probe._position(Math.Matrix(current.matrix).translation, 'entity matrix'),
            model_matrix_position=probe._position(Math.Matrix(current.model.matrix).translation, 'model matrix'),
            own_matrix_position=probe._position(Math.Matrix(player.getOwnVehicleMatrix()).translation, 'own matrix'),
            speed_info=[probe._number(speed[i], -10000, 10000, 'native speed') for i in range(4)],
            left_contacts=probe._integer(current.filter.numLeftTrackContacts, 0, 128, 'left contacts'),
            right_contacts=probe._integer(current.filter.numRightTrackContacts, 0, 128, 'right contacts'),
            native_received_filter_input='UNKNOWN', native_controlled_property='UNKNOWN')

    def move(self, flags, is_key_down, owner_id):
        import Avatar
        import BigWorld
        if (type(flags) not in probe.integer_types or (flags, is_key_down) not in ((1, True), (0, False))
                or type(is_key_down) is not bool):
            raise ValueError('only the explicit original start/stop command pair is authorized')
        _move_binding()
        player = BigWorld.player()
        if type(player) is not Avatar.PlayerAvatar or id(player) != owner_id or player.id != vehicle.AVATAR_ID:
            raise RuntimeError('original command owner changed')
        # Do not assign isOnArena, invoke native callbacks, or change the method.
        player.moveVehicle(flags, is_key_down)

    def request(self, basename):
        self.pixels.request(basename)

    def screenshot(self, basename):
        return self.pixels.screenshot(basename)


def _position(value):
    if type(value) is not list or len(value) != 3:
        raise ValueError('three actual numeric position components required')
    return [probe._number(x, -100000, 100000, 'position') for x in value]


def _near(value, target):
    return all(abs(value[i] - target[i]) <= XZ_TOLERANCE for i in (0, 2))


class _Scenario(ready._Scenario):
    # This frozen method checks only actual entity identity/model/lifecycle;
    # its PREBATTLE-specific advance/timer validators are never called.
    def __init__(self, record, native, clock=None):
        self.record, self.native, self.clock = record, native, _now if clock is None else clock
        self.advances, self.sequence = 0, 0
        self.notes, self.open_calls, self.pairs, self.seen = [], {}, [], set()
        self.note_error = None
        self.active, self.complete, self.geometry = False, False, None
        self.avatar_owner = self.vehicle_owner = None
        self.ready_since = self.last_ready = self.last_time = self.last_server_time = None
        self.ready_samples, self.phase = 0, 'waiting_world'
        self.movement_notes, self.movement_open, self.movement_pairs, self.movement_seen = [], {}, [], set()
        self.movement_error, self.movement_sequence = None, 0
        self.pending_png, self.png_advance, self.screenshots = None, None, []
        self.started_at = self.stopped_at = self.hold_since = None
        self.forward_attempted = self.stop_attempted = False
        self.forward_pair = self.stop_pair = None
        self.intent = None
        value, identity = native.account()
        if (value['player_is_original_account'] is not True or value['native_connected'] is not True
                or value['repository_present'] is not True or not vehicle._int(value['repository_owner_id'], 1)
                or value['entity_id'] != identity['entity_id'] or value['name'] != identity['name']
                or identity['database_id'] != 1):
            raise RuntimeError('actual connected primary Account required')
        self.account, self.repository = dict(identity), value['repository_owner_id']
        self.expected = native.expected_vehicle()
        native.initialize()
        self.active = True
        _emit(record, 'arena_movement_armed', account=self.account, repository_owner_id=self.repository,
            expected_vehicle=self.expected, sources=native.sources, movement_sources=native.movement_sources,
            lab_origin=list(ORIGIN), lab_target=list(TARGET), xz_tolerance=XZ_TOLERANCE,
            maximum_command_seconds=MAX_COMMAND_SECONDS, minimum_hold_seconds=MIN_HOLD_SECONDS,
            max_advances=MAX_ADVANCES, screenshot_basenames=list(SCREENSHOTS),
            clock_modified=False, entity_position_assigned=False, computer_input=False,
            physics_acceptance='NOT_RUN', native_entity_created_by_scenario=False)

    def note_movement(self, phase, method, line, offset, call_id, owner_id, data):
        if not self.active or type(method) not in probe.string_types or method != 'moveVehicle':
            return False
        try:
            if (type(phase) not in probe.string_types or phase not in ('call', 'return')
                    or type(data) is not dict or set(data) != set(('flags', 'is_key_down'))
                    or type(data['is_key_down']) is not bool):
                raise ValueError('exact movement callback schema required')
            if len(self.movement_notes) >= MAX_MOVEMENT_PENDING or self.movement_sequence >= MAX_MOVEMENT_NOTES:
                raise ValueError('movement callback budget exhausted')
            row = dict(phase=phase, method=method, source_line=probe._integer(line, 1, 100000, 'line'),
                offset=probe._integer(offset, -1, 100000, 'offset'),
                call_id=probe._integer(call_id, 1, 2147483647, 'call ID'),
                owner_id=probe._integer(owner_id, 1, 0x7fffffffffffffff, 'owner ID'),
                data=dict(flags=probe._integer(data['flags'], 0, 63, 'flags'), is_key_down=data['is_key_down']),
                noted_at=probe._number(self.clock(), 0, 1e10, 'note clock'), intent=self.intent)
            self.movement_sequence += 1
            row['sequence'] = self.movement_sequence
            self.movement_notes.append(row)
            return True
        except (ValueError, TypeError, UnicodeError) as error:
            if self.movement_error is None:
                self.movement_error = 'invalid passive movement note: ' + type(error).__name__
            return False

    def drain_movement(self):
        if self.movement_error:
            raise RuntimeError(self.movement_error)
        pending, self.movement_notes = self.movement_notes, []
        for note in pending:
            _emit(self.record, 'arena_movement_callback', **note)
            if (note['source_line'] != 2130 or note['owner_id'] != self.avatar_owner
                    or note['offset'] not in ((-1,) if note['phase'] == 'call' else (12, 345))):
                raise RuntimeError('original movement callback identity or offset differs')
            cid = note['call_id']
            if note['phase'] == 'call':
                if cid in self.movement_seen:
                    raise RuntimeError('duplicate movement call ID')
                self.movement_seen.add(cid)
                self.movement_open[cid] = note
                continue
            entry = self.movement_open.pop(cid, None)
            if entry is None or any(entry[key] != note[key] for key in ('method', 'owner_id', 'data', 'intent')):
                raise RuntimeError('original movement return lacks its exact entry')
            pair = dict(entry=entry, returned=note)
            if note['intent'] is not None:
                if note['offset'] != 345:
                    raise RuntimeError('explicit command returned before original transport call')
                expected = {'forward': (1, True), 'stop': (0, False)}[note['intent']]
                if (note['data']['flags'], note['data']['is_key_down']) != expected:
                    raise RuntimeError('original explicit movement arguments differ')
                attr = 'forward_pair' if note['intent'] == 'forward' else 'stop_pair'
                if getattr(self, attr) is not None:
                    raise RuntimeError('duplicate explicit movement command')
                setattr(self, attr, pair)
            # Move01 measured the original startup stop before __isOnArena:
            # exact automatic (0, False) returns12 without reaching the RPC.
            # Keep that passive pair, never use it as forward/stop proof.
            elif note['data'] != {'flags': 0, 'is_key_down': False}:
                raise RuntimeError('unexpected non-diagnostic movement input')
            self.movement_pairs.append(pair)

    def command(self, name, now):
        if name == 'forward':
            if self.forward_attempted:
                raise RuntimeError('forward command already attempted')
            self.forward_attempted, self.started_at = True, now
            args = (1, True)
        elif name == 'stop':
            if not self.forward_attempted or self.stop_attempted:
                raise RuntimeError('stop must follow exactly one forward attempt')
            self.stop_attempted, self.stopped_at = True, now
            args = (0, False)
        else:
            raise ValueError('unsupported movement action')
        self.intent = name
        try:
            _emit(self.record, 'arena_movement_command', phase='begin', action=name,
                advance=self.advances, observed_at=now, flags=args[0], is_key_down=args[1], owner_id=self.avatar_owner)
            self.native.move(args[0], args[1], self.avatar_owner)
            _emit(self.record, 'arena_movement_command', phase='return', action=name,
                advance=self.advances, observed_at=now, flags=args[0], is_key_down=args[1], owner_id=self.avatar_owner)
        finally:
            self.intent = None
        self.drain_movement()
        if (self.forward_pair if name == 'forward' else self.stop_pair) is None:
            raise RuntimeError('explicit method invocation lacks passive original callback proof')

    def emergency_stop(self):
        if self.forward_attempted and not self.stop_attempted:
            self.command('stop', probe._number(self.clock(), 0, 1e10, 'stop clock'))

    def advance(self):
        if self.complete:
            return True
        if not self.active:
            raise RuntimeError('failed movement cannot continue')
        self.advances += 1
        if self.advances > MAX_ADVANCES:
            raise RuntimeError('movement observation budget exhausted')
        now = probe._number(self.clock(), 0, 1e10, 'diagnostic clock')
        if self.last_time is not None and now < self.last_time:
            raise RuntimeError('diagnostic clock moved backwards')
        self.last_time = now
        self.drain()
        value, current, motion = self.native.observe(), self.native.vehicle(), self.native.motion()
        world_ready = self.world_ready(value, current)
        # Establish actual Avatar identity before draining an automatic period3
        # command that may have occurred between observation callbacks.
        self.drain_movement()
        _emit(self.record, 'arena_movement_state', advance=self.advances, observed_at=now,
            phase=self.phase, observation=value, vehicle=current, motion=motion, world_ready=world_ready)
        if not world_ready:
            if self.pending_png is not None or self.forward_attempted:
                raise RuntimeError('native world lost readiness during movement')
            self.ready_since = self.last_ready = None
            self.ready_samples = 0
            return False
        if self.last_ready is not None and now - self.last_ready > MAX_GAP:
            raise RuntimeError('movement observation gap exceeded')
        if not motion.get('present') or motion.get('period') != 3:
            if self.pending_png is not None or self.forward_attempted or motion.get('period', 0) > 3:
                raise RuntimeError('test-lab BATTLE phase lost')
            self.ready_since = self.last_ready = None
            self.ready_samples = 0
            return False
        if (motion['owner_id'] != self.avatar_owner or motion['vehicle_owner_id'] != self.vehicle_owner
                or motion['period_end_time'] != 160.0 or motion['period_length'] != 60.0
                or motion['additional_info_is_none'] is not True or motion['is_on_arena'] is not True
                or motion['cruise_mode'] != 0 or current['roster']['avatar_ready'] is not True):
            raise RuntimeError('actual movement phase/owner differs from bounded test policy')
        server_time = probe._number(motion['server_time'], 99.0, 158.0, 'native server time')
        if self.last_server_time is not None and server_time < self.last_server_time:
            raise RuntimeError('native server clock moved backwards')
        self.last_server_time = server_time
        if self.ready_since is None:
            self.ready_since = now
        self.last_ready, self.ready_samples = now, self.ready_samples + 1
        pos = _position(motion['entity_position'])
        for key in ('entity_matrix_position', 'model_matrix_position', 'own_matrix_position'):
            _position(motion[key])
        if (abs(pos[0]-ORIGIN[0]) > XZ_TOLERANCE or pos[2] < ORIGIN[2]-XZ_TOLERANCE
                or pos[2] > TARGET[2]+XZ_TOLERANCE):
            raise RuntimeError('native entity escaped bounded server path')
        if not self.forward_attempted and not _near(pos, ORIGIN):
            raise RuntimeError('native position changed before authorized forward command')
        if self.forward_attempted and not self.stop_attempted and now-self.started_at >= MAX_COMMAND_SECONDS:
            raise RuntimeError('original stop was not reached within movement budget')
        if self.phase in ('hold', 'after_png') and not _near(pos, TARGET):
            raise RuntimeError('native target changed after original stop')
        if self.phase == 'waiting_world':
            if self.ready_samples >= 3 and now-self.ready_since >= MIN_BASELINE_SECONDS:
                self.phase = 'before_png'
                self._request(SCREENSHOTS[0], now)
            return False
        if self.pending_png is not None:
            screenshot = self.native.screenshot(self.pending_png)
            if screenshot is None:
                if self.advances-self.png_advance >= MAX_PNG_ADVANCES:
                    raise RuntimeError('actual movement PNG budget exhausted')
                return False
            if (type(screenshot) is not dict or screenshot.get('basename') != self.pending_png
                    or screenshot.get('png_container_valid') is not True):
                raise ValueError('actual owned native PNG required')
            self.screenshots.append(screenshot)
            _emit(self.record, 'arena_movement_screenshot', advance=self.advances, observed_at=now, **screenshot)
            self.pending_png = None
            if len(self.screenshots) == 1:
                self.command('forward', now)
                self.phase = 'wait_target'
                return False
            self.complete, self.active, self.phase = True, False, 'complete'
            _emit(self.record, 'arena_movement_complete', advance=self.advances, observed_at=now,
                avatar_owner_id=self.avatar_owner, vehicle_owner_id=self.vehicle_owner,
                forward_call_id=self.forward_pair['returned']['call_id'],
                stop_call_id=self.stop_pair['returned']['call_id'],
                forward_at=self.started_at, stopped_at=self.stopped_at, hold_began_at=self.hold_since,
                hold_seconds=now-self.hold_since, screenshots=2, lab_target=list(TARGET),
                native_position_observed=True, server_authority_acceptance='NOT_RUN',
                physics_acceptance='NOT_RUN', native_pixel_acceptance='NOT_RUN',
                clean_teardown_acceptance='NOT_RUN', compatibility_acceptance=False)
            return True
        if self.phase == 'wait_target' and _near(pos, TARGET):
            self.command('stop', now)
            self.phase, self.hold_since = 'hold', now
            return False
        if self.phase in ('hold', 'after_png'):
            if self.phase == 'hold' and now-self.hold_since >= MIN_HOLD_SECONDS:
                self.phase = 'after_png'
                self._request(SCREENSHOTS[1], now)
        return False

    def _request(self, basename, now):
        self.native.request(basename)
        self.pending_png, self.png_advance = basename, self.advances
        _emit(self.record, 'arena_movement_screenshot_requested', advance=self.advances,
            observed_at=now, basename=basename, writer='BigWorld.screenShot', pixel_acceptance='NOT_RUN')


def arm(record, settings):
    global _run, _native, _arm_attempted
    if _arm_attempted or _closing:
        raise RuntimeError('movement scenario already armed or closing')
    _arm_attempted = True
    _native = _Native(record, settings)
    _run = _Scenario(record, _native)


def note_avatar_call(phase, method, line, offset, call_id, owner_id, entity_id, space_id):
    if _run is None or _closing:
        return False
    return _run.note('avatar', phase, method, line, offset, call_id, owner_id, entity_id, space_id)


def note_vehicle_call(phase, method, line, offset, call_id, owner_id, entity_id, space_id):
    if _run is None or _closing:
        return False
    return _run.note('vehicle', phase, method, line, offset, call_id, owner_id, entity_id, space_id)


def note_geometry_mapped(space_id, path):
    if _run is None or _closing:
        return False
    return _run.note_geometry(space_id, path)


def note_movement_call(phase, method, line, offset, call_id, owner_id, data):
    if _run is None or _closing:
        return False
    return _run.note_movement(phase, method, line, offset, call_id, owner_id, data)


def advance(record):
    if _run is None or _closing:
        return False
    try:
        return _run.advance()
    except Exception as error:
        stop_error = None
        try:
            _run.emergency_stop()
        except Exception as stopping:
            stop_error = type(stopping).__name__
        _run.active = False
        _emit(record, 'arena_movement_error', advance=_run.advances, error_type=type(error).__name__,
            stop_error_type=stop_error, forward_attempted=_run.forward_attempted,
            stop_attempted=_run.stop_attempted, completion=False, compatibility_acceptance=False)
        raise


def fini(record, native_cleanup):
    """Stop any outstanding intent, then try every original cleanup and report errors."""
    global _closing, _finished_cleanup
    if _finished_cleanup:
        if _cleanup_errors:
            raise RuntimeError('movement cleanup previously failed: ' + ', '.join(_cleanup_errors))
        return
    # If the user closes during movement, this is an explicit original stop,
    # not a killed process. Root may already have disabled passive profiler
    # notes during fini, in which case missing proof remains a cleanup failure.
    if _run is not None and _run.forward_attempted and not _run.stop_attempted:
        try:
            _run.emergency_stop()
        except Exception as error:
            _cleanup_errors.append('stop_before_cleanup:' + type(error).__name__)
    _closing = True
    stages = [('before_entities', arena_bootstrap.fini_before_entities),
              ('native_hangar_cleanup', native_cleanup), ('after_entities', arena_bootstrap.fini_after_entities)]
    if _native is not None:
        stages.append(('light_after_native', _native.light_fini))
    for name, function in stages:
        failed = None
        try:
            function()
        except Exception as error:
            failed = type(error).__name__
            _cleanup_errors.append(name + ':' + failed)
        try:
            _emit(record, 'arena_movement_cleanup', stage=name, outcome='FAIL' if failed else 'PASS', error_type=failed)
        except Exception as error:
            _cleanup_errors.append(name + ':record:' + type(error).__name__)
    _finished_cleanup = True
    if _cleanup_errors:
        raise RuntimeError('movement cleanup failed: ' + ', '.join(_cleanup_errors))
