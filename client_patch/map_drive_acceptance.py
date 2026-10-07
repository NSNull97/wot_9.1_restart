# -*- coding: utf-8 -*-
"""Explicit dual-mode diagnostic: full phase2 drive or a separate Prohorovka boundary leg.

No native callback, pose, clock, filter or UI state is manufactured here. Only
the installed original FightButton, moveVehicle and leaveArena paths are called.
No native acceptance is implied by synthetic tests of this candidate.
"""
import hashlib
import json
import math
import os

import arena_entry_probe as probe
import arena_movement_scenario as movement
import arena_vehicle_scenario as vehicle
import map_drive_scenario as binding
from account_switch_scenario import _Native as AccountNative
from ms1_crew_scenario import _Native as ScreenshotNative, _now

VERSION, PHASE_VERSION = 1, 2
MODES = ('phase2_drive', 'boundary_only')
BOUNDARY_VERSION = 1
MAX_RIDES, MAX_RIDE_ADVANCES = 8, 360
MAX_ADVANCES, MAX_GAP, MAX_PNG_ADVANCES = MAX_RIDES * MAX_RIDE_ADVANCES, 3.0, 15
MAX_PENDING, MAX_NOTES = 256, 8 * 16384
HOLD_SECONDS, HOLD_TOLERANCE, STOP_SPEED = 3.0, 0.05, 0.1
FORWARD_METRES, REVERSE_METRES, TURN_RADIANS = 3.0, 2.0, 0.15
MAX_ACTION_SECONDS = 30.0
MAX_PREQUEUE_ACCOUNT_SECONDS = 30.0
SCREENSHOTS = tuple('map_drive_r%02d_%s' % (ride, moment)
                    for ride in range(1, MAX_RIDES + 1)
                    for moment in ('entry', 'driven', 'return'))
ROUTE_PLAN_SHA256 = 'f0102395b10f1d5529d4d8bae366b2a9c6cd0fc3db5cfe871d921900d9123c5c'
ROUTE_SPAWN = (-63.499908447265625, 22.416676, -440.81304931640625)
ROUTE_TARGET = (-77.033447265625, 0.0, -389.29127502441406)
MAX_ROUTE_STEPS, ROUTE_MIN_INTERVAL, ROUTE_MAX_INTERVAL = 100, 1.0, 1.5
MAX_ROUTE_RETRIES, MAX_ROUTE_TOTAL_RETRIES = 6, 600
ROUTE_MAX_TILT = math.pi / 6.0  # Explicit diagnostic safety bound, not historical tuning.
ROUTE_BACKOFF_METRES = 12.0
SAMPLE_DELAY, MAX_SAMPLES, MAX_SAMPLE_SECONDS = 0.02, 1600, 45.0
SAMPLER_VERSION = 1
MAX_TOTAL_SAMPLES = MAX_RIDES * MAX_SAMPLES
ROUTE_POLICY_VERSION = 3  # Current native filter feedback; offline raw-speed proof is separate.
BOUNDARY_PLAN_SHA256 = '375ee30671c665d9f760239b2a26a2b72614819ec279b0678dabdc538b90a99e'
BOUNDARY_SPAWN = (-15.0, 13.322001, 10.0)  # Only XZ/yaw checked; Y settles natively.
BOUNDARY_MAX_SECONDS, BOUNDARY_MAX_STEPS = 110.0, 111
BOUNDARY_MIN_INTERVAL, BOUNDARY_MAX_INTERVAL = 1.0, 1.5
BOUNDARY_MAX_RETRIES, BOUNDARY_MAX_TOTAL_RETRIES = 6, 660
BOUNDARY_MAX_TILT = math.pi / 6.0
BOUNDARY_BACKOFF_METRES, BOUNDARY_STALL_SECONDS = 5.0, 5.0
BOUNDARY_STOP_HOLD_SECONDS = 3.0
BOUNDARY_Z_MIN, BOUNDARY_Z_MAX = 497.5, 499.0
BOUNDARY_STALL_SPEED, BOUNDARY_STALL_RADIUS = 0.15, 0.05
BOUNDARY_SCREENSHOTS = tuple('map_boundary_r%02d_%s' % (ride, moment)
                             for ride in range(1, MAX_RIDES + 1) for moment in ('entry', 'end', 'return'))
BOUNDARY_COMMANDS = {'boundary_stop': (0, False), 'boundary_backoff': (2, True),
                     'boundary_backoff_stop': (0, False), 'error_stop': (0, False)}
MAPS = {1: '01_karelia', 4: '05_prohorovka'}
RETURN_HANGAR_PATH = 'spaces/hangar_v2'
LEAVE_METHOD = ('leaveArena', 'leaveArena', 2310, 1,
                '47261da3df3dc5f139d3c073a79652ba57f4d2884ccafe99312598d6f852382e')
CAPTCHA_REQUIRED_METHOD = ('isCaptchaRequired', 'isCaptchaRequired', 148, 1,
                           'cecb673a7b4d31aa7e639cea3376e0ca2c3c6fc676d1d1888d77e2600829c34e')
CAPTCHA_REQUIRED_SOURCE = 'scripts/client/gui/game_control/captcha_control.py'
CACHE_GETTER_METHOD = ('getCacheValue', 'getCacheValue', 81, 3,
                       'b951284723a5172d7ace0a7c3ad7687c26765f96a16174deeaf20b1126b6d183')
CACHE_GETTER_SOURCE = 'scripts/client/gui/shared/utils/requesters/abstract.py'
EXTRA_SOURCES = (
    ('res/scripts/client/gui/Scaleform/daapi/view/lobby/LobbyView.pyc',
     '6170e0a23b0bacd7c062d2c15452fdd0d03710cd6cb3ecfe447904782f8a2b57'),
    ('res/scripts/client/gui/Scaleform/daapi/view/lobby/header/LobbyHeader.pyc',
     'b94bad0587c1a7f03bc8240a9add4e1dbbe54c35d18460cafcf220039da695b4'),
    ('res/' + CAPTCHA_REQUIRED_SOURCE[:-3] + '.pyc',
     '09ac1aa482c7394d7790a26a04281af870a3da71ef397c2c4de35865736eb334'),
    ('res/' + CACHE_GETTER_SOURCE[:-3] + '.pyc',
     'dc62be9eb3808e217099575f9be9e0a6c1edfe49b39f3cdb0c8da2c07933b65f'),
    ('res/scripts/client/gui/ClientHangarSpace.pyc',
     'b7b5e86d72d21bc9423c36189db7158f96b8e684718d58e6929a4ec1537e1b64'),
    ('res/scripts/client/game.pyc',
     '2f2057748cbbbaefe21c5fd434cc1492bd08521f705f43832e45e493af6896c1'),
    ('res/scripts/client/gui/Scaleform/framework/managers/containers.pyc',
     '2eeb5825c15b99f1acacaec06db376973ecbfe37164172bd042c48b4e970753a'),
    ('res/scripts/client/AvatarInputHandler/cameras.pyc',
     '3da204c302f7443087332faebd976724420dfe8861f3166d22357c866931ee85'),
)
RAY_PLANS = {
    1: (binding.RAY_PLAN_SHA256, binding.GROUND_RAYS),
    4: ('103d4b34edee017d82d7ed5ac7fbd9ff624521e3095d65f49133830f6e09a89c', (
        ('spawn', -15.0, 10.0), ('east5', -10.0, 10.0), ('west5', -20.0, 10.0),
        ('north5', -15.0, 15.0), ('south5', -15.0, 5.0),
        ('other_triangle', -14.300000190734863, 10.899999618530273),
        ('rock_top', -36.3427619934082, 9.45744800567627))),
}
COMMANDS = {'forward': (1, True), 'turn': (9, True), 'stop_turn': (0, False),
            'reverse': (2, True), 'stop_reverse': (0, False), 'error_stop': (0, False),
            'route_stop': (0, False), 'route_backoff': (2, True), 'route_backoff_stop': (0, False)}
COMMON_ACTIONS = ('fight', 'forward', 'turn', 'stop_turn', 'reverse', 'stop_reverse', 'leave')
ALLOWED_MOVES = set(COMMANDS.values()) | set(((5, True),))
ENTITY_METHODS = dict((kind, dict(methods)) for kind, methods in vehicle.CALLBACKS.items())
ENTITY_METHODS['avatar'].update({'__init__': (110, (212,)), 'onBecomePlayer': (147, (882,))})
_run = None
_attempted = _closing = False


def _emit(record, event, **fields):
    fields.update(version=VERSION, phase_version=PHASE_VERSION)
    raw = json.dumps(fields, ensure_ascii=True, sort_keys=True, allow_nan=False)
    if len(raw.encode('ascii')) > 16384:
        raise ValueError('acceptance record exceeds bounded primitive budget')
    record(event, **fields)


def _int(value, low=1, high=0x7fffffffffffffff):
    return probe._integer(value, low, high, 'diagnostic integer')


def _callback_handle(value):
    # #717 callback f4f66f returns signed PyInt (486ee0); the generator's
    # high byte cycles through bit31. cancelCallback f4f6c0 parses signed 'i'.
    # Zero is the native scheduling-failure sentinel, never a returned handle.
    if type(value) is not int or value == 0 or not -2147483648 <= value <= 2147483647:
        scalar = str(value) if type(value) is int and -0x8000000000000000 <= value <= 0x7fffffffffffffff else '<unsupported>'
        raise ValueError('native callback handle requires nonzero signed int32: ' + scalar)
    return value


def _vector(value):
    return binding._position(value)


def _distance(a, b):
    return math.sqrt(sum((a[i] - b[i]) ** 2 for i in (0, 2)))


def _along(a, b, axis):
    return sum((a[i] - b[i]) * axis[i] for i in (0, 2))


def _heading_delta(a, b):
    return math.atan2(math.sin(a - b), math.cos(a - b))


class _RoutePlan(object):
    """Read-only feedback policy; returns full original flags, never sets pose."""
    def __init__(self, position, heading, now):
        if _distance(position, ROUTE_SPAWN) > 0.5 or abs(_heading_delta(heading, 0.0)) > 0.05:
            raise RuntimeError('measured route requires actual configured Karelia spawn/yaw')
        self.started_at = now
        self.last_at = self.last_position = self.last_flags = None
        self.steps, self.stalled, self.braking, self.path_metres = 0, 0, False, 0.0

    def sample(self, position, heading, speed, tilt, now):
        position = _vector(position)
        heading = probe._number(heading, -math.pi, math.pi, 'route heading')
        speed = probe._number(speed, -100.0, 100.0, 'route speed')
        tilt = probe._number(tilt, 0.0, math.pi, 'body tilt')
        if tilt > ROUTE_MAX_TILT:
            raise RuntimeError('bounded route body tilt exceeded')
        if self.steps >= MAX_ROUTE_STEPS:
            raise RuntimeError('measured route feedback budget exhausted')
        dt, displacement = None, None
        if self.last_at is not None:
            dt = now - self.last_at
            if not ROUTE_MIN_INTERVAL <= dt <= ROUTE_MAX_INTERVAL:
                raise RuntimeError('route missed its declared one-second observation window')
            displacement = _distance(position, self.last_position)
            self.path_metres += displacement
        progress, distance = _distance(position, ROUTE_SPAWN), _distance(position, ROUTE_TARGET)
        candidate = (self.last_flags not in (None, 0) and progress >= 40.0 and distance < 12.0
                     and abs(speed) < 0.15 and displacement is not None and displacement < 0.25)
        self.stalled = self.stalled + 1 if candidate else 0
        if abs(speed) > 2.0:
            self.braking = True
        elif abs(speed) < 1.3:
            self.braking = False
        error = _heading_delta(math.atan2(ROUTE_TARGET[0] - position[0], ROUTE_TARGET[2] - position[2]), heading)
        flags = 0 if self.braking else (5 if error < -0.05 else (9 if error > 0.05 else 1))
        done = self.stalled >= 5
        row = dict(sample_index=self.steps + 1, observed_at=now, elapsed=now - self.started_at,
                   interval_seconds=dt, position=position, heading=heading, speed=speed, tilt_radians=tilt,
                   previous_flags=self.last_flags, displacement=displacement, progress_metres=progress,
                   target_distance=distance, path_metres=self.path_metres, heading_error=error,
                   braking=self.braking, stalled_intervals=self.stalled, flags=0 if done else flags,
                   stop_candidate=done, collision_authority='NOT_RUN_REQUIRES_INDEPENDENT_WORKER_GEOMETRY')
        self.steps += 1
        self.last_at, self.last_position, self.last_flags = now, position, row['flags']
        return row


class _BoundaryPlan(object):
    def __init__(self, position, heading, now):
        if _distance(position, BOUNDARY_SPAWN) > 0.5 or abs(_heading_delta(heading, 0.0)) > 0.05:
            raise RuntimeError('boundary requires unchanged Prohorovka settled spawn/yaw')
        self.started_at = now
        self.last_at, self.last_position = None, None
        self.steps = 0
        self.stable_since = self.stall_anchor = None

    def sample(self, position, speed, tilt, now):
        position = _vector(position)
        speed = probe._number(speed, -1000, 1000, 'current native filter speed')
        tilt = probe._number(tilt, 0, math.pi, 'actual native body-up tilt')
        now = probe._number(now, 0, 1e10, 'boundary observation clock')
        if tilt > BOUNDARY_MAX_TILT:
            raise RuntimeError('native boundary body-up tilt exceeds thirty degrees')
        if not 0 <= now-self.started_at < BOUNDARY_MAX_SECONDS or self.steps >= BOUNDARY_MAX_STEPS:
            raise RuntimeError('bounded boundary forward exhausted without measured stop')
        dt = None if self.last_at is None else now-self.last_at
        if dt is not None and not BOUNDARY_MIN_INTERVAL <= dt <= BOUNDARY_MAX_INTERVAL:
            raise RuntimeError('actual boundary renewal/sample gap differs')
        near = -500.0 < position[0] < 500.0 and BOUNDARY_Z_MIN <= position[2] <= BOUNDARY_Z_MAX
        valid = (self.steps > 0 and near and abs(speed) <= BOUNDARY_STALL_SPEED
                 and _distance(position, BOUNDARY_SPAWN) >= 450.0)
        if not valid:
            self.stable_since = self.stall_anchor = None
        elif self.stable_since is None or _distance(position, self.stall_anchor) > BOUNDARY_STALL_RADIUS:
            self.stable_since, self.stall_anchor = now, position
        stop = valid and now-self.stable_since >= BOUNDARY_STALL_SECONDS
        self.steps += 1
        self.last_at, self.last_position = now, position
        return dict(sample_index=self.steps, observed_at=now, interval_seconds=dt,
                    started_at=self.started_at, elapsed_seconds_boundary=now-self.started_at,
                    position=position, speed=speed, tilt_radians=tilt, near_wall=near,
                    low_speed_sample=valid, stable_since=self.stable_since,
                    stable_seconds=0.0 if self.stable_since is None else now-self.stable_since,
                    stop_candidate=stop, renewed_flags=None if stop else 1,
                    collision_authority='NOT_RUN_REQUIRES_INDEPENDENT_WORKER_WALL_GEOMETRY')


def _sample_pose(matrix):
    # Copy/read only. Preserve the raw forward vector; no normalization, Euler
    # reinterpretation, native provider assignment or camera update occurs.
    return dict(position=probe._position(matrix.translation, 'sample position'),
                forward=probe._position(matrix.applyToAxis(2), 'sample forward'))


def _checked_captcha(value):
    fields = ('battles_till_captcha', 'captcha_required', 'controller_owner_id',
              'stats_owner_id', 'guard_blocked_calls')
    if type(value) is not dict or set(value) != set(fields):
        raise ValueError('exact passive CAPTCHA precondition fields required')
    _int(value['battles_till_captcha'], 1, 1)  # Exact ordinary server policy v1.
    _int(value['controller_owner_id'])
    _int(value['stats_owner_id'])
    if (value['captcha_required'] is not False
            or type(value['guard_blocked_calls']) not in probe.integer_types
            or value['guard_blocked_calls'] != 0):
        raise RuntimeError('native CAPTCHA is required or external CAPTCHA guard was invoked')
    return dict(value)


def _audit_sources():
    rows = binding._audit_sources() + vehicle._audit_sources()
    root = os.path.normcase(os.path.realpath(os.getcwd()))
    for relative, expected in EXTRA_SOURCES:
        path = os.path.join(root, *relative.split('/'))
        if (not os.path.normcase(os.path.realpath(path)).startswith(root + os.sep)
                or os.path.islink(path) or not os.path.isfile(path)
                or not 1 <= os.path.getsize(path) <= 1048576):
            raise ValueError('bounded original action source required')
        with open(path, 'rb') as stream:
            raw = stream.read(1048577)
        if len(raw) > 1048576 or hashlib.sha256(raw).hexdigest() != expected:
            raise ValueError('original action source differs')
        rows.append(dict(relative_path=relative, bytes=len(raw), sha256=expected))
    return rows


class _Pixels(ScreenshotNative):
    def request(self, basename):
        import BigWorld
        if basename not in SCREENSHOTS + BOUNDARY_SCREENSHOTS or basename in self.requested:
            raise ValueError('one owned screenshot per acceptance basename required')
        names = self._entries()
        if any(not any(name.startswith(prefix + '_') and name.endswith('.png')
                       for prefix in self.requested) for name in names):
            raise ValueError('acceptance screenshot directory contains unowned files')
        if any(name.startswith(basename + '_') for name in names):
            raise ValueError('acceptance screenshot already exists')
        self.requested.add(basename)
        BigWorld.screenShot('png', basename)


class _Native(binding._Native):
    def __init__(self, settings):
        # The unchanged read-only getters below are Python2 unbound methods:
        # their receiver must really derive from the declaring helper classes.
        # Do not call the inherited initializer: ordinary mode owns services.
        self.pixels, self.accounts = _Pixels(settings), AccountNative(settings)

    def initialize(self):
        import Avatar
        import hangar_capabilities
        import map_drive_client as ordinary
        if not ordinary.is_active():
            raise RuntimeError('explicit ordinary drive policy must already be installed')
        ordinary._controller._require_owned()
        ordinary._audit_originals(hangar_capabilities, ordinary._controller.guard)
        sources = _audit_sources() + ordinary._audit_sources(hangar_capabilities)
        binding._bindings()
        movement._move_binding()
        probe._code_contract(Avatar.PlayerAvatar.leaveArena, LEAVE_METHOD)
        return sources

    def context(self):
        return probe._collect_observation()

    def hangar_ready(self):
        import Account
        import BigWorld
        from ConnectionManager import connectionManager
        from gui.shared import g_itemsCache
        from gui.WindowsManager import g_windowsManager
        from gui.Scaleform.framework import ViewTypes
        from gui.Scaleform.Waiting import Waiting
        from gui.Scaleform.daapi.view.lobby.hangar.Hangar import Hangar
        player = BigWorld.player()
        if (type(player) is not Account.PlayerAccount or getattr(player, 'databaseID', None) is None
                or not connectionManager.isConnected() or not g_itemsCache.isSynced()):
            return False
        app = g_windowsManager.window
        if app is None or app.containerManager is None:
            return False
        container = app.containerManager.getContainer(ViewTypes.LOBBY_SUB)
        if container is None:  # Original getContainer387 returns None at29.
            return False
        page = container.getView()
        return type(page) is Hangar and page.flashObject is not None and not Waiting.isVisible()

    def account(self):
        import Account
        import BigWorld
        import ms1_ammo_probe
        if not self.hangar_ready():
            raise RuntimeError('real ready native Hangar required before account snapshot')
        state = self.accounts.state()
        ammo = ms1_ammo_probe._collect_native()
        player = BigWorld.player()
        return dict(account=state['account'], selected_inventory_id=state['selected_inventory_id'],
                    ammo=ammo['observation'], player_owner_id=id(player),
                    entity_id=player.id, repository_owner_id=id(Account.g_accountRepository),
                    hangar_owner_id=state['hangar_owner'], crew_owner_id=state['crew_owner'])

    def select_ms1(self):
        self.accounts.select_ms1()

    def _button(self):
        from gui.WindowsManager import g_windowsManager
        from gui.Scaleform.framework import ViewTypes
        from gui.Scaleform.daapi.view.lobby.LobbyView import LobbyView
        from gui.Scaleform.daapi.view.lobby.header.LobbyHeader import LobbyHeader
        from gui.Scaleform.daapi.view.lobby.header.FightButton import FightButton
        import map_drive_client as ordinary
        if not self.hangar_ready() or not ordinary.is_active():
            raise RuntimeError('original Hangar and ordinary policy required')
        ordinary._controller._require_owned()
        lobby = g_windowsManager.window.containerManager.getContainer(ViewTypes.VIEW).getView()
        if type(lobby) is not LobbyView or lobby.flashObject is None:
            raise RuntimeError('original bound LobbyView required')
        header = lobby.components['lobbyHeader']
        if type(header) is not LobbyHeader or header.flashObject is None:
            raise RuntimeError('original bound LobbyHeader required')
        button = header.components['fightButton']
        if type(button) is not FightButton or button.flashObject is None:
            raise RuntimeError('original bound FightButton required')
        enabled = probe._boolean(button.flashObject.button.enabled, 'actual FightButton.enabled')
        eligibility = ordinary._controller.native.eligibility()
        if not enabled or not eligibility['allowed'] or eligibility['queued']:
            raise RuntimeError('native random entry is not enabled for selected actual MS1')
        return button

    def button_state(self):
        button = self._button()
        return dict(owner_id=id(button), class_name='FightButton', flash_bound=True,
                    enabled=True, map_id=0, action_name='')

    def captcha_state(self):
        from gui import game_control
        from gui.game_control.captcha_control import CaptchaController
        from gui.shared import g_itemsCache
        import map_drive_client as ordinary
        if not self.hangar_ready() or not g_itemsCache.isSynced():
            raise RuntimeError('synced original Hangar required for CAPTCHA precondition')
        ordinary._captcha_guard.require_ready()
        captcha, stats = game_control.g_instance.captcha, g_itemsCache.items.stats
        if type(captcha) is not CaptchaController:
            raise RuntimeError('original CAPTCHA controller instance required')
        probe._code_contract(captcha.isCaptchaRequired, CAPTCHA_REQUIRED_METHOD, CAPTCHA_REQUIRED_SOURCE)
        probe._code_contract(stats.getCacheValue, CACHE_GETTER_METHOD, CACHE_GETTER_SOURCE)
        # Read actual sync data and the original controller result separately.
        # Never set the counter, answer a CAPTCHA or remove the original aspect.
        counter = stats.getCacheValue('battlesTillCaptcha', None)
        required = captcha.isCaptchaRequired()
        return _checked_captcha(dict(battles_till_captcha=counter, captcha_required=required,
            controller_owner_id=id(captcha), stats_owner_id=id(stats),
            guard_blocked_calls=ordinary._captcha_guard.blocked_calls))

    def fight(self, expected_owner):
        button = self._button()
        if id(button) != expected_owner:
            raise RuntimeError('native FightButton changed before invocation')
        self.captcha_state()  # Fresh check immediately before the original call.
        # PrebattleAction's random-map default is integer zero. Explicit None
        # survives JoinRandomQueueCtx and fails original doCmdInt3 argument 5.
        button.fightClick(0, '')

    def world(self):
        return vehicle._Native.vehicle(self)

    def motion(self):
        import BigWorld
        import Math
        data = movement._Native.motion(self)
        if data.get('present'):
            current = BigWorld.entity(vehicle.VEHICLE_ID)
            body = Math.Matrix(current.filter.bodyMatrix)
            forward = probe._position(body.applyToAxis(2), 'body forward axis')
            up = probe._position(body.applyToAxis(1), 'body up axis')
            length = math.sqrt(forward[0] ** 2 + forward[2] ** 2)
            up_length = math.sqrt(sum(v * v for v in up))
            if not 0.1 <= length <= 2.0 or not 0.1 <= up_length <= 2.0:
                raise RuntimeError('native body forward axis is degenerate')
            data.update(forward_axis=[forward[0] / length, 0.0, forward[2] / length],
                        heading=math.atan2(forward[0], forward[2]), body_up_axis=up,
                        tilt_radians=math.acos(max(-1.0, min(1.0, up[1] / up_length))))
        return data

    def binding(self):
        return binding._Native.binding(self)

    def sample(self, owner, vehicle_owner, space_id):
        import Avatar
        import BigWorld
        import Math
        import Vehicle
        player, current = BigWorld.player(), BigWorld.entity(vehicle.VEHICLE_ID)
        if (type(player) is not Avatar.PlayerAvatar or id(player) != owner
                or type(current) is not Vehicle.Vehicle or id(current) != vehicle_owner
                or player.spaceID != space_id or current.spaceID != space_id
                or not player.inWorld or not current.inWorld or not current.isStarted
                or player.vehicle is not current or player.playerVehicleID != current.id
                or type(current.filter) is not BigWorld.WGVehicleFilter):
            raise RuntimeError('passive sampler native lifetime/attachment changed')
        provider, filt = player.getOwnVehicleMatrix(), current.filter
        target = provider.target
        camera = BigWorld.camera()
        if camera is None or current.model is None:
            raise RuntimeError('passive sampler camera/model absent')
        # Original cameras.getWorldRayAndPoint208 reads this inverse view
        # matrix at113..119. It is camera world pose, not the view matrix.
        result = dict(player_owner_id=id(player), vehicle_owner_id=id(current),
            player_entity_id=player.id, vehicle_entity_id=current.id, space_id=space_id,
            entity_position=probe._position(current.position, 'sample Entity position'),
            entity_matrix=_sample_pose(Math.Matrix(current.matrix)),
            model=_sample_pose(Math.Matrix(current.model.matrix)),
            body=_sample_pose(Math.Matrix(filt.bodyMatrix)),
            own=_sample_pose(Math.Matrix(provider)),
            target_present=target is not None,
            target=None if target is None else _sample_pose(Math.Matrix(target)),
            camera=_sample_pose(Math.Matrix(camera.invViewMatrix)),
            camera_class=probe._text(type(camera).__name__, 64, 'native camera class'),
            speed_info=binding._vector(filt.speedInfo.value, 4, 'sample filter speeds'),
            last_server_speeds=binding._vector(player._PlayerAvatar__lastVehicleSpeeds, 2, 'sample last server speeds'))
        if BigWorld.player() is not player or BigWorld.entity(current.id) is not current:
            raise RuntimeError('native lifetime changed during passive sample')
        return result

    def schedule_sample(self, delay, callback):
        import BigWorld
        return BigWorld.callback(delay, callback)

    def cancel_sample(self, callback_id):
        import BigWorld
        BigWorld.cancelCallback(callback_id)

    def ground(self, map_id, context):
        import Avatar
        import BigWorld
        import Math
        player = BigWorld.player()
        if (type(player) is not Avatar.PlayerAvatar or id(player) != context['player_owner_id']
                or player.spaceID != context['space_id'] or player.arena.arenaType.id != map_id):
            raise RuntimeError('actual native map changed before passive ground queries')
        plan, samples = RAY_PLANS[map_id]
        rows = []
        for name, x, z in samples:
            start, end = [x, 200.0, z], [x, -50.0, z]
            result = BigWorld.wg_collideSegment(player.spaceID, Math.Vector3(*start), Math.Vector3(*end), 18)
            rows.append(dict(sample_id=name, start=start, end=end, flags=18, result=binding._ray_result(result)))
        if BigWorld.player() is not player or player.arena.arenaType.id != map_id:
            raise RuntimeError('native map changed during passive ground queries')
        return dict(map_id=map_id, geometry=MAPS[map_id], space_id=player.spaceID,
                    player_owner_id=id(player), source_sample_plan_sha256=plan,
                    samples=rows, ground_comparison_acceptance='NOT_RUN', state_assigned=False)

    def move(self, flags, is_key_down, owner):
        import Avatar
        import BigWorld
        if type(flags) not in probe.integer_types or type(is_key_down) is not bool or (flags, is_key_down) not in ALLOWED_MOVES:
            raise ValueError('only approved native drive/route movement commands are allowed')
        movement._move_binding()
        player = BigWorld.player()
        if type(player) is not Avatar.PlayerAvatar or id(player) != owner or not player.isOnArena:
            raise RuntimeError('current original Avatar movement owner required')
        player.moveVehicle(flags, is_key_down)

    def leave(self, owner):
        import Avatar
        import BigWorld
        player = BigWorld.player()
        probe._code_contract(Avatar.PlayerAvatar.leaveArena, LEAVE_METHOD)
        if type(player) is not Avatar.PlayerAvatar or id(player) != owner or not player.isOnArena:
            raise RuntimeError('current original Avatar leave owner required')
        player.leaveArena()

    def request(self, name):
        self.pixels.request(name)

    def screenshot(self, name):
        return self.pixels.screenshot(name)


class _Sampler(object):
    """Requested 50Hz read cadence, not a render-frame or motion controller."""
    def __init__(self, run, space_id):
        self.run, self.space_id = run, space_id
        self.ride_index = run.ride_index
        self.avatar_owner, self.vehicle_owner = run.avatar_owner, run.vehicle_owner
        self.started_at = probe._number(run.clock(), 0, 1e10, 'sampler start')
        self.active, self.callback_id, self.count = True, None, 0
        self.error = self.last_sampled_at = None
        self.stop_recorded = self.negative_handle_recorded = False
        run.emit('sampler_start', sampler_version=SAMPLER_VERSION, observed_at=self.started_at,
                 requested_delay=SAMPLE_DELAY, max_samples=MAX_SAMPLES,
                 max_seconds=MAX_SAMPLE_SECONDS, frame_aligned=False,
                 window='basic_drive_after_route', sampler_index=run.sampler_count,
                 process_max_samplers=MAX_RIDES, process_max_samples=MAX_TOTAL_SAMPLES,
                 camera_source='Math.Matrix(BigWorld.camera().invViewMatrix)',
                 player_owner_id=run.avatar_owner, vehicle_owner_id=run.vehicle_owner,
                 space_id=space_id, native_state_assigned=False)

    def _tick(self):
        self.callback_id = None  # This owned callback has now fired.
        if not self.active:
            return
        try:
            run = self.run
            if (not run.active or run.complete or run.ride_index != self.ride_index
                    or run.sampler is not self or run.avatar_owner != self.avatar_owner
                    or run.vehicle_owner != self.vehicle_owner
                    or run.phase not in ('entry_png', 'route_backoff_hold', 'forward', 'turn',
                                         'hold_turn', 'reverse', 'hold_reverse', 'driven_png')):
                raise RuntimeError('passive sampler outlived its owned arena')
            before = probe._number(run.clock(), 0, 1e10, 'sample start')
            if (self.count >= MAX_SAMPLES or run.total_samples >= MAX_TOTAL_SAMPLES
                    or before - self.started_at >= MAX_SAMPLE_SECONDS):
                raise RuntimeError('passive sampler finite observation budget exhausted')
            value = run.native.sample(run.avatar_owner, run.vehicle_owner, self.space_id)
            after = probe._number(run.clock(), before, 1e10, 'sample end')
            if self.last_sampled_at is not None and before <= self.last_sampled_at:
                raise RuntimeError('passive sample time is not strictly increasing')
            run.emit('sample', sampler_version=SAMPLER_VERSION, sample_index=self.count + 1,
                     sample_started_at=before, sampled_at=after, requested_delay=SAMPLE_DELAY,
                     previous_sampled_at=self.last_sampled_at, snapshot=value,
                     last_update=run.sample_last_update, last_deferred=run.sample_last_deferred)
            self.count += 1
            run.total_samples += 1
            self.last_sampled_at = after
            # Retain ownership before checking the return value. A failed
            # validation must not discard an already scheduled callback.
            self.callback_id = run.native.schedule_sample(SAMPLE_DELAY, self._tick)
            _callback_handle(self.callback_id)
            if self.callback_id < 0 and not self.negative_handle_recorded:
                run.emit('sampler_callback_handle', sampler_version=SAMPLER_VERSION,
                         observed_at=run.clock(), callback_handle=self.callback_id,
                         native_type='int', first_negative=True)
                self.negative_handle_recorded = True
        except Exception as error:
            # The BigWorld callback must not leak an exception or turn a read
            # failure into a successful sample. advance() fails and owns quit.
            self.error = type(error).__name__ + ': ' + str(error)[:256]
            self.active = False

    def stop(self, reason):
        if self.stop_recorded:
            return
        self.active = False
        callback_id = self.callback_id
        if callback_id is not None:
            self.run.native.cancel_sample(callback_id)
            self.callback_id = None  # Keep it available for fini if cancel raises.
        self.run.emit('sampler_stop', sampler_version=SAMPLER_VERSION, reason=reason,
                      observed_at=self.run.clock(), sample_count=self.count,
                      sampler_index=self.run.sampler_count, process_sample_count=self.run.total_samples,
                      started_at=self.started_at, last_sampled_at=self.last_sampled_at,
                      pending_callback_cancelled=callback_id is not None,
                      callback_handle=(callback_id if type(callback_id) is int
                                       and -2147483648 <= callback_id <= 2147483647 else None),
                      error=self.error)
        self.stop_recorded = True


class _Scenario(object):
    diagnostic_mode = 'phase2_drive'
    def __init__(self, record, settings, native=None, clock=None):
        self.record, self.clock = record, _now if clock is None else clock
        self.native = _Native(settings) if native is None else native
        self.phase, self.advances, self.sequence = 'initial', 0, 0
        self.ride_index, self.ride_advances = 1, 0
        self.completed_rides, self.maps_seen, self.spaces_seen, self.arenas_seen = [], set(), set(), set()
        self.space_id = self.arena_id = None
        self.route = None
        self.route_done = False
        self.route_retries = self.route_total_retries = 0
        self.route_commands, self.commands = [], dict(COMMANDS)
        self.all_screenshots = []
        self.screen_names = SCREENSHOTS[:3]
        self.active, self.complete, self.moving = True, False, False
        self.last_time = self.last_world = self.stable_since = self.anchor = None
        self.hold_phase = None
        self.avatar_owner = self.vehicle_owner = self.initial = self.map_id = None
        self.geometry = self.latest_update = self.latest_bound = None
        self.return_geometry = self.pending_return_geometry = None
        self.intent = self.note_error = self.png = self.command_at = None
        self.fight_at = None
        self.next_delay = 1.0
        self.sampler = None
        self.sampler_count = self.total_samples = 0
        self.sample_last_update = self.sample_last_deferred = None
        self.notes, self.open_calls, self.seen, self.pairs = [], {}, set(), []
        self.proofs, self.screenshots = {}, []
        self.selected = self.ground_done = False
        self.sources = self.native.initialize()
        self.emit('armed', sources=self.sources, maps=dict((str(k), v) for k, v in MAPS.items()),
                  max_advances=MAX_ADVANCES, maximum_action_seconds=MAX_ACTION_SECONDS,
                  max_rides=MAX_RIDES, max_ride_advances=MAX_RIDE_ADVANCES,
                  route_plan_sha256=ROUTE_PLAN_SHA256, route_feedback_budget=MAX_ROUTE_STEPS,
                  route_policy_version=ROUTE_POLICY_VERSION,
                  route_speed_source='original_WGVehicleFilter.speedInfo[0]',
                  offline_raw_speed_equivalence='NOT_CLAIMED',
                  route_interval_bounds=[ROUTE_MIN_INTERVAL, ROUTE_MAX_INTERVAL],
                  max_route_retries_per_decision=MAX_ROUTE_RETRIES,
                  max_route_total_retries=MAX_ROUTE_TOTAL_RETRIES,
                  route_backoff_metres=ROUTE_BACKOFF_METRES,
                  maximum_prequeue_account_seconds=MAX_PREQUEUE_ACCOUNT_SECONDS,
                  forward_metres=FORWARD_METRES, turn_radians=TURN_RADIANS, reverse_metres=REVERSE_METRES,
                  minimum_hold_seconds=HOLD_SECONDS, hold_tolerance_metres=HOLD_TOLERANCE,
                  max_samplers=MAX_RIDES, max_samples_per_ride=MAX_SAMPLES,
                  max_process_samples=MAX_TOTAL_SAMPLES, sampler_window='basic_drive_after_route',
                  physical_input=False, services_owner='map_drive_client', full_card_acceptance='NOT_RUN')

    def emit(self, suffix, **fields):
        fields.setdefault('phase', self.phase)
        fields.setdefault('diagnostic_mode', self.diagnostic_mode)
        if self.diagnostic_mode == 'boundary_only':
            fields.setdefault('boundary_version', BOUNDARY_VERSION)
        fields.setdefault('ride_index', self.ride_index)
        fields.update(scenario_phase=self.phase, advance=self.advances, ride_advance=self.ride_advances)
        _emit(self.record, 'map_drive_acceptance_' + suffix, **fields)

    def note(self, kind, phase, method, line, offset, call_id, owner_id, data):
        if not self.active:
            return False
        try:
            if phase not in ('call', 'return') or type(phase) not in probe.string_types:
                raise ValueError('exact original callback phase required')
            if len(self.notes) >= MAX_PENDING or self.sequence >= MAX_NOTES:
                raise ValueError('bounded acceptance callback budget exhausted')
            if kind == 'binding':
                if method not in binding.RETURNS:
                    raise ValueError('unknown original binding method')
                clean = binding._callback_data(method, data)
            elif kind == 'movement':
                if method != 'moveVehicle' or type(data) is not dict or set(data) != set(('flags', 'is_key_down')):
                    raise ValueError('exact original movement data required')
                clean = dict(flags=_int(data['flags'], 0, 63), is_key_down=probe._boolean(data['is_key_down'], 'key down'))
            elif kind == 'action':
                if (method == 'fightClick' and type(data) is dict
                        and set(data) == set(('mapID', 'actionName'))
                        and type(data['mapID']) in probe.integer_types
                        and data['mapID'] == 0 and data['actionName'] == ''):
                    clean = {'mapID': 0, 'actionName': ''}
                elif method == 'leaveArena' and type(data) is dict and not data:
                    clean = {}
                else:
                    raise ValueError('exact original action arguments required')
            elif kind in ('avatar', 'vehicle'):
                if method not in ENTITY_METHODS[kind] or type(data) is not dict or set(data) != set(('entity_id', 'space_id')):
                    raise ValueError('exact original Entity metadata required')
                clean = dict(entity_id=_int(data['entity_id'], 1, 2147483647),
                             space_id=None if data['space_id'] is None else _int(data['space_id'], 0, 4294967295))
            else:
                raise ValueError('unknown acceptance callback kind')
            row = dict(kind=kind, phase=phase, method=method, source_line=_int(line, 1, 100000),
                       offset=_int(offset, -1, 100000), call_id=_int(call_id), owner_id=_int(owner_id),
                       data=clean, intent=(self.intent if
                           (kind == 'movement' and self.intent in self.commands or
                            kind == 'action' and self.intent in ('fight', 'leave')) else None),
                       noted_at=probe._number(self.clock(), 0, 1e10, 'note time'))
            self.sequence += 1
            row['sequence'] = self.sequence
            row['ride_index'] = self.ride_index
            self.notes.append(row)
            if kind == 'binding' and phase == 'return':
                anchor = dict(call_id=row['call_id'], owner_id=row['owner_id'],
                              source_line=row['source_line'], offset=row['offset'],
                              noted_at=row['noted_at'], sequence=row['sequence'])
                if method == 'updateOwnVehiclePosition' and line == 1445 and offset == 198:
                    self.sample_last_update = anchor
                elif method == '__setOwnVehicleMatrixCallback' and line == 2951 and offset in (151, 179):
                    self.sample_last_deferred = anchor
            return True
        except (ValueError, TypeError, UnicodeError) as error:
            if self.note_error is None:
                self.note_error = 'invalid acceptance callback: ' + type(error).__name__
            return False

    def note_geometry(self, space_id, path):
        if not self.active:
            return False
        try:
            space_id = _int(space_id, 1, 4294967295)
            path = probe._text(path, 128, 'mapped geometry')
            if path == RETURN_HANGAR_PATH:
                if (self.phase != 'waiting_return' or self.geometry is None
                        or space_id == self.geometry['space_id'] or 'leave' not in self.proofs
                        or self.return_geometry is not None or self.pending_return_geometry is not None):
                    raise ValueError('one separate native Hangar after explicit leave required')
                # Native teardown notes may await advance(). Validate them there,
                # against this boundary, without invoking callbacks or raising here.
                self.pending_return_geometry = dict(space_id=space_id, path=path,
                    noted_at=probe._number(self.clock(), 0, 1e10, 'geometry time'),
                    after_callback_sequence=self.sequence, ride_index=self.ride_index)
                return True
            if self.geometry is not None or space_id in self.spaces_seen:
                raise ValueError('one fresh positive native space per ride required')
            if path not in ['spaces/' + v for v in MAPS.values()]:
                raise ValueError('native geometry outside tested server map pool')
            if self.phase != 'waiting_world':
                raise ValueError('geometry arrived outside the pending original fight')
            self.space_id = space_id
            self.geometry = dict(space_id=space_id, path=path, noted_at=self.clock(), ride_index=self.ride_index)
            return True
        except (ValueError, TypeError, UnicodeError) as error:
            if self.note_error is None:
                self.note_error = 'invalid native geometry: ' + type(error).__name__
            return False

    def drain(self):
        if self.note_error:
            raise RuntimeError(self.note_error)
        notes, self.notes = self.notes, []
        for row in notes:
            self.emit('callback', **row)
            if row['ride_index'] != self.ride_index:
                raise RuntimeError('late callback belongs to a previous ride')
            kind, method = row['kind'], row['method']
            if kind == 'binding':
                line, returns = binding.RETURNS[method]
            elif kind == 'movement':
                line, returns = 2130, (12, 345)
            elif kind == 'action':
                line, returns = (196, (65,)) if method == 'fightClick' else (2310, (178,))
            else:
                line, returns = ENTITY_METHODS[kind][method]
                if row['data']['entity_id'] != (vehicle.AVATAR_ID if kind == 'avatar' else vehicle.VEHICLE_ID):
                    raise RuntimeError('foreign Entity callback identity')
            if row['source_line'] != line or row['offset'] not in ((-1,) if row['phase'] == 'call' else returns):
                raise RuntimeError('original callback source/normal offset differs')
            key = row['call_id']
            if row['phase'] == 'call':
                if key in self.seen:
                    raise RuntimeError('duplicate original callback ID')
                self.seen.add(key)
                self.open_calls[key] = row
                continue
            entry = self.open_calls.pop(key, None)
            if entry is None or any(entry[k] != row[k] for k in ('kind', 'method', 'source_line', 'owner_id', 'data', 'intent', 'ride_index')):
                raise RuntimeError('original callback return lacks unchanged entry')
            pair = {'entry': entry, 'returned': row}
            if kind == 'avatar' and method == '__init__':
                fight = self.proofs.get('fight')
                if (self.phase != 'waiting_world' or fight is None
                        or entry['sequence'] <= fight['returned']['sequence']):
                    raise RuntimeError('fresh Avatar constructor must follow this ride original fight')
            if kind == 'binding':
                constructors = [p['returned'] for p in self.pairs if p['returned']['kind'] == 'avatar'
                                and p['returned']['method'] == '__init__' and p['returned']['offset'] == 212]
                if (len(constructors) != 1 or constructors[0]['owner_id'] != row['owner_id']
                        or entry['sequence'] <= constructors[0]['sequence']):
                    raise RuntimeError('provider callback lacks a fresh current-ride Avatar constructor')
                if method == 'updateOwnVehiclePosition':
                    self.latest_update, self.latest_bound = pair, None
                elif row['offset'] == 151:
                    if self.latest_update is None or entry['sequence'] <= self.latest_update['returned']['sequence']:
                        raise RuntimeError('original binding success lacks prior update')
                    self.latest_bound = pair
            elif kind in ('action', 'movement') and row['intent'] is not None:
                intent = row['intent']
                if intent in self.proofs:
                    raise RuntimeError('duplicate explicit original action')
                if kind == 'movement':
                    if intent not in self.commands or row['offset'] != 345 or tuple(row['data'][k] for k in ('flags', 'is_key_down')) != self.commands[intent]:
                        raise RuntimeError('explicit movement did not reach original transport call')
                elif (intent, method) not in (('fight', 'fightClick'), ('leave', 'leaveArena')):
                    raise RuntimeError('original action is unrelated to diagnostic intent')
                self.proofs[intent] = pair
            elif kind == 'movement' and row['data'] != {'flags': 0, 'is_key_down': False}:
                raise RuntimeError('unexpected non-diagnostic movement command')
            if kind in ('avatar', 'vehicle'):
                if method in ('onLeaveWorld', 'onBecomeNonPlayer', 'stopVisual') and self.phase not in ('waiting_return', 'return_hold', 'return_png', 'complete'):
                    raise RuntimeError('native world left before explicit original leave')
                if len(self.pairs) >= 64:
                    raise RuntimeError('Entity callback pair budget exhausted')
                self.pairs.append(pair)

        if self.pending_return_geometry is not None:
            mapped = self.pending_return_geometry
            if mapped['ride_index'] != self.ride_index:
                raise RuntimeError('return geometry belongs to a previous ride')
            leave = self.proofs['leave']['returned']
            if leave['owner_id'] != self.avatar_owner:
                raise RuntimeError('native Hangar mapping has foreign leave owner')
            ids = []
            for kind, method, offset in (('avatar', 'onLeaveWorld', 948), ('avatar', 'onBecomeNonPlayer', 193),
                                         ('vehicle', 'stopVisual', 177), ('vehicle', 'onLeaveWorld', 48)):
                matches = [p for p in self.pairs if p['returned']['kind'] == kind
                           and p['returned']['method'] == method and p['returned']['offset'] == offset]
                if len(matches) != 1:
                    raise RuntimeError('native Hangar mapping lacks exact original teardown')
                entry, returned = matches[0]['entry'], matches[0]['returned']
                owner = self.avatar_owner if kind == 'avatar' else self.vehicle_owner
                if (returned['owner_id'] != owner or entry['sequence'] <= leave['sequence']
                        or returned['sequence'] > mapped['after_callback_sequence']
                        or entry['noted_at'] < leave['noted_at'] or returned['noted_at'] > mapped['noted_at']):
                    raise RuntimeError('native Hangar mapping preceded own original teardown')
                ids.append(returned['call_id'])
            self.return_geometry, self.pending_return_geometry = mapped, None
            self.emit('return_geometry', geometry=mapped, leave_call_id=leave['call_id'],
                      teardown_call_ids=ids, hangar_ready_proven=False)

    def action(self, name, now, owner):
        if name == 'leave' and self.sampler is not None:
            self.sampler.stop('before_original_leave')
        if name == 'fight':
            self.emit('captcha', observed_at=now,
                      snapshot=_checked_captcha(self.native.captcha_state()),
                      original_counter_assigned=False, original_result_overridden=False)
        if name in self.proofs or self.intent is not None:
            raise RuntimeError('one original action per named phase required')
        self.intent = name
        if name in self.commands and self.commands[name][0]:
            self.moving = True  # Keep stop ownership even if the invocation fails.
            self.command_at = now
        try:
            self.emit('action', moment='begin', action=name, owner_id=owner, observed_at=now,
                      arguments=list(self.commands[name]) if name in self.commands else None)
            if name == 'fight':
                self.native.fight(owner)
            elif name == 'leave':
                self.native.leave(owner)
            else:
                self.native.move(self.commands[name][0], self.commands[name][1], owner)
            self.emit('action', moment='return', action=name, owner_id=owner, observed_at=now)
        finally:
            self.intent = None
        self.drain()
        pair = self.proofs.get(name)
        if pair is None or pair['returned']['owner_id'] != owner:
            raise RuntimeError('explicit original action lacks its passive exact-owner callback proof')
        if name in self.commands and self.commands[name][0] == 0:
            self.moving = False

    def _account(self, value):
        if (value['account']['database_id'] != 1 or value['selected_inventory_id'] != 1
                or value['ammo']['raw_shells'] != [2570, 20, 2826, 0, 3082, 0]):
            raise RuntimeError('actual primary MS1 public inventory/20 AP required')
        if self.initial is not None:
            for key in ('account', 'selected_inventory_id', 'ammo', 'repository_owner_id'):
                if value[key] != self.initial[key]:
                    raise RuntimeError('native warm-return invariant changed: ' + key)

    def _world_ready(self, context, state, motion, attached):
        if not context['player_is_original_avatar']:
            return False
        if self.avatar_owner is None:
            self.avatar_owner = context['player_owner_id']
        if context['player_owner_id'] != self.avatar_owner:
            raise RuntimeError('Avatar owner changed within one drive')
        map_id = context['arena_type_id']
        if map_id is not None and map_id not in MAPS:
            raise RuntimeError('server selected an unsupported native map')
        if (context['in_world'] is True and self.space_id is not None
                and context['space_id'] != self.space_id):
            raise RuntimeError('actual native world changed the bound ride space')
        if not (context['native_connected'] and context['in_world'] is True
                and self.space_id is not None and context['space_id'] == self.space_id
                and context['steps_till_init'] == 0 and context['user_sees_world'] is True
                and context['space_load_progress'] == 1.0 and state['vehicle_present']
                and state['in_world'] is True and state['is_started'] is True and motion.get('present')):
            return False
        if (context['repository_owner_id'] != self.initial['repository_owner_id']
                or context['name'] != self.initial['account']['name'] or context['player_vehicle_id'] != vehicle.VEHICLE_ID
                or context['geometry_name'] != MAPS[map_id] or context['geometry_path'] != 'spaces/' + MAPS[map_id]
                or self.geometry is None or self.geometry['path'] != context['geometry_path']
                or self.geometry['space_id'] != context['space_id']):
            raise RuntimeError('native map/own identity/geometry differs')
        arena_id = _int(context['arena_unique_id'])
        if self.arena_id is None:
            if arena_id in self.arenas_seen:
                raise RuntimeError('native arena identity reused across completed rides')
            self.arena_id = arena_id
        elif arena_id != self.arena_id:
            raise RuntimeError('native arena identity changed inside a ride')
        if self.map_id is not None and map_id != self.map_id:
            raise RuntimeError('native arena map changed without return')
        self.map_id = map_id
        if self.vehicle_owner is None:
            self.vehicle_owner = state['owner_id']
        if (state['owner_id'] != self.vehicle_owner or state['entity_id'] != vehicle.VEHICLE_ID
                or state['health'] != 90 or vehicle._native_flag(state['crew_active']) != 1 or state['type_compact_descr'] != 3329
                or state['descriptor_sha256'] != self.initial['account']['vehicles'][0]['compact_descr_sha256']
                or state['public_descriptor_sha256'] != state['descriptor_sha256']
                or not state['avatar_descriptor_same'] or state['model_count'] != 4
                or not all(m['present'] and m['visible'] for m in state['models'])
                or not state['entity_model_is_chassis'] or not state['battle_original']
                or not state['battle_movie_present'] or not state['battle_component_visible']
                or not state['turret_sound_initialized']):
            raise RuntimeError('original own MS1 models/descriptor/health/Battle differ')
        roster = state['roster']
        if (roster is None or roster['database_id'] != 1 or roster['name'] != context['name']
                or roster['alive'] is not True):
            raise RuntimeError('native own roster identity/alive state differs')
        if roster['avatar_ready'] is not True:
            # Original ClientArena.__onAvatarReady334 changes this flag only
            # when the separate server AVATAR_READY update arrives. A loaded
            # world can precede that reply (Ride06); it is not accepted ready.
            if (roster['avatar_ready'] is False and self.phase == 'waiting_world'
                    and self.last_world is None and motion['period'] == 1
                    and motion['is_on_arena'] is False):
                return False
            raise RuntimeError('native own roster readiness differs or was lost')
        if (motion['owner_id'] != self.avatar_owner or motion['vehicle_owner_id'] != self.vehicle_owner
                or motion['period'] != 3 or motion['is_on_arena'] is not True):
            return False
        required = [('avatar', '__init__', 212), ('avatar', 'onBecomePlayer', 882),
                    ('avatar', 'onEnterWorld', 316), ('avatar', 'onSpaceLoaded', 33),
                    ('avatar', '__onInitStepCompleted', 640), ('vehicle', 'onEnterWorld', 169),
                    ('vehicle', 'startVisual', 407)]
        for kind, method, offset in required:
            matches = [p['returned'] for p in self.pairs if p['returned']['kind'] == kind
                       and p['returned']['method'] == method and p['returned']['offset'] == offset]
            if not matches:
                return False
            if len(matches) != 1 or matches[0]['owner_id'] != (self.avatar_owner if kind == 'avatar' else self.vehicle_owner):
                raise RuntimeError('original native lifecycle owner/uniqueness differs')
            if method not in ('__init__', 'onBecomePlayer') and matches[0]['data']['space_id'] != self.space_id:
                raise RuntimeError('original lifecycle callback belongs to another native space')
        if (not attached.get('present') or attached['owner_id'] != self.avatar_owner
                or attached['vehicle_owner_id'] != self.vehicle_owner):
            return False
        if not (attached['attached_is_own_vehicle'] and attached['attached_vehicle_id'] == vehicle.VEHICLE_ID
                and attached['attached_owner_id'] == self.vehicle_owner and attached['filter_is_original_wg_vehicle']
                and attached['target_present'] and self.latest_bound is not None):
            return False
        if (self.latest_bound['returned']['owner_id'] != self.avatar_owner
                or self.latest_update['returned']['owner_id'] != self.avatar_owner):
            raise RuntimeError('provider callbacks belong to another Avatar')
        if (not binding._near(_vector(attached['own_matrix_position']), _vector(attached['body_matrix_position']))
                or not binding._near(_vector(attached['target_position']), _vector(attached['body_matrix_position']), (0, 1, 2), 0.002)
                or not binding._near(_vector(attached['own_matrix_position']), _vector(motion['own_matrix_position']), (0, 1, 2), 0.002)):
            raise RuntimeError('native provider no longer follows actual filter body')
        return True

    def capture(self, name, now):
        if self.png is not None:
            raise RuntimeError('one outstanding native screenshot required')
        self.native.request(name)
        self.png = (name, self.advances)
        self.emit('screenshot_request', basename=name, observed_at=now)

    def receipt(self, now):
        image = self.native.screenshot(self.png[0])
        if image is None:
            if self.advances - self.png[1] >= MAX_PNG_ADVANCES:
                raise RuntimeError('native screenshot did not produce bounded valid PNG')
            return False
        self.emit('screenshot', observed_at=now, image=image)
        self.screenshots.append(image)
        self.all_screenshots.append(dict(ride_index=self.ride_index, basename=image['basename'], sha256=image['sha256']))
        self.png = None
        return True

    def _hold(self, motion, now):
        # Begin only on a valid stationary observation. Never count the last
        # violating-speed sample as part of a stopped interval (Ride16 review).
        position = _vector(motion['own_matrix_position'])
        speed = probe._number(motion['speed_info'][0], -1000, 1000, 'native hold speed')
        if self.hold_phase != self.phase:
            self.hold_phase = self.phase
            self.stable_since, self.anchor = None, None
        if abs(speed) > STOP_SPEED:
            self.stable_since, self.anchor = None, None
            return False
        if self.stable_since is None or self.anchor is None or _distance(position, self.anchor) > HOLD_TOLERANCE:
            self.stable_since, self.anchor = now, position
            return False
        return now-self.stable_since >= HOLD_SECONDS

    def _complete_ride(self, now):
        required = set(COMMON_ACTIONS)
        if self.route is not None:
            required.update(self.route_commands)
            required.update(('route_stop', 'route_backoff', 'route_backoff_stop'))
            if not self.route_done:
                raise RuntimeError('Karelia route/backoff remains incomplete')
        if self.open_calls or self.notes or self.moving or set(self.proofs) != required:
            raise RuntimeError('one exact complete original action/lifecycle chain per ride required')
        if len(self.screenshots) != 3 or [r['basename'] for r in self.screenshots] != list(self.screen_names):
            raise RuntimeError('each complete ride needs its own three native PNGs')
        if self.space_id in self.spaces_seen or self.arena_id in self.arenas_seen:
            raise RuntimeError('completed native world identity reused')
        if (self.sampler is None or self.sampler.active or self.sampler.callback_id is not None
                or self.sampler.error is not None or not self.sampler.stop_recorded
                or self.sampler.ride_index != self.ride_index or self.sampler.count < 1
                or self.sampler_count != self.ride_index):
            raise RuntimeError('one measured and stopped owned sampler per completed ride required')
        self.maps_seen.add(self.map_id)
        self.spaces_seen.add(self.space_id)
        self.arenas_seen.add(self.arena_id)
        summary = dict(ride_index=self.ride_index, map_id=self.map_id, space_id=self.space_id,
                       arena_unique_id=self.arena_id, fight_at=self.fight_at, returned_at=now,
                       action_count=len(self.proofs), route_observed=self.route is not None,
                       sampler_index=self.sampler_count, sample_count=self.sampler.count)
        self.completed_rides.append(summary)
        self.emit('ride_complete', observed_at=now, summary=summary, screenshots=self.screenshots,
                  action_call_ids=dict((k, v['returned']['call_id']) for k, v in self.proofs.items()),
                  account_invariant=True, completed_rides=len(self.completed_rides),
                  random_maps_seen=sorted(self.maps_seen))
        if len(self.completed_rides) >= 2 and self.maps_seen == set(MAPS) and self.route_done:
            self.phase, self.complete = 'complete', True
            self.emit('complete', observed_at=now, rides=self.completed_rides, screenshots=self.all_screenshots,
                      account_invariant=True, native_rides=len(self.completed_rides),
                      two_maps_observed=True, original_route_commands_observed=True,
                      sampler_count=self.sampler_count, process_sample_count=self.total_samples,
                      collision_acceptance='NOT_RUN_REQUIRES_INDEPENDENT_SERVER_GEOMETRY',
                      physical_input_acceptance='NOT_RUN')
            return True
        if self.ride_index >= MAX_RIDES:
            raise RuntimeError('bounded random-map coverage exhausted without both original maps')
        self.phase = 'between_rides'
        return False

    def _next_ride(self):
        if self.notes or self.open_calls or self.png is not None or self.moving:
            raise RuntimeError('previous ride retains callbacks, PNG, or movement ownership')
        if (self.sampler is None or self.sampler.active or self.sampler.callback_id is not None
                or not self.sampler.stop_recorded or self.sampler.error is not None
                or self.ride_index >= MAX_RIDES):
            raise RuntimeError('previous sampler must be stopped before bounded reentry')
        self.ride_index += 1
        self.ride_advances = 0
        self.phase = 'initial'
        self.last_world = self.stable_since = self.anchor = None
        self.hold_phase = None
        self.avatar_owner = self.vehicle_owner = self.map_id = None
        self.geometry = self.latest_update = self.latest_bound = None
        self.return_geometry = self.pending_return_geometry = None
        self.intent = self.png = self.command_at = self.fight_at = None
        self.sampler = None
        self.sample_last_update = self.sample_last_deferred = None
        self.space_id = self.arena_id = None
        self.pairs, self.proofs, self.screenshots = [], {}, []
        self.selected = self.ground_done = False
        self.commands, self.route_commands, self.route = dict(COMMANDS), [], None
        self.screen_names = SCREENSHOTS[(self.ride_index - 1) * 3:self.ride_index * 3]
        self.emit('next_ride', previous_world_references_released=True, ordinary_services_reinitialized=False,
                  process_callback_sequence=self.sequence, seen_maps=sorted(self.maps_seen),
                  previous_sampler_stopped=True, process_samplers=self.sampler_count,
                  process_sample_count=self.total_samples)

    def _start_basic_drive(self, position, axis, now):
        if (self.sampler is not None or self.sampler_count >= MAX_RIDES
                or self.sampler_count != self.ride_index - 1):
            raise RuntimeError('one bounded sampler for each basic drive required')
        self.sampler_count += 1
        self.sampler = _Sampler(self, self.space_id)
        self.sampler._tick()
        if self.sampler.error is not None:
            raise RuntimeError('passive sampler failed: ' + self.sampler.error)
        self.origin, self.axis = position, axis
        self.action('forward', now, self.avatar_owner)
        self.phase = 'forward'

    def _route_step(self, motion, attached, now):
        # B retains only the initial update1445. Its stored speeds may therefore
        # be stale; current original filter feedback is the route control input.
        # This is an explicit native policy change from the offline raw-speed run.
        filtered = motion['speed_info']
        if type(filtered) not in (list, tuple) or len(filtered) != 4:
            raise RuntimeError('four actual native filter speeds required')
        filtered = [probe._number(v, -1000.0, 1000.0, 'native filter speed') for v in filtered]
        speeds = attached['last_server_speeds']
        if type(speeds) not in (list, tuple) or len(speeds) != 2:
            raise RuntimeError('two actual original server speeds required')
        raw_speed = probe._number(speeds[0], -1000.0, 1000.0, 'original server speed')
        raw_rotation = probe._number(speeds[1], -1000.0, 1000.0, 'original server rotation speed')
        if self.latest_update is None or self.latest_bound is None:
            raise RuntimeError('route speed lacks original update/binding callbacks')
        returned = self.latest_update['returned']
        if (returned['owner_id'] != self.avatar_owner
                or [raw_speed, raw_rotation] != [returned['data']['speed'], returned['data']['rspeed']]):
            raise RuntimeError('route speed differs from latest own original callback')
        row = self.route.sample(_vector(motion['own_matrix_position']), motion['heading'],
                                filtered[0], motion['tilt_radians'], now)
        self.emit('route_sample', route_policy_version=ROUTE_POLICY_VERSION,
                  speed_source='original_WGVehicleFilter.speedInfo[0]',
                  filter_speed_info=filtered, last_server_speeds=[raw_speed, raw_rotation],
                  last_server_speeds_used_for_control=False,
                  own_update_call_id=returned['call_id'], own_update_noted_at=returned['noted_at'],
                  own_update_age_seconds=now-returned['noted_at'], **row)
        if row['stop_candidate']:
            self.action('route_stop', now, self.avatar_owner)
            self.phase, self.anchor, self.stable_since = 'route_hold', row['position'], now
            return
        name = 'route_%03d' % row['sample_index']
        self.commands[name] = (row['flags'], row['flags'] != 0)
        self.route_commands.append(name)
        self.action(name, now, self.avatar_owner)

    def _route_due(self, now, ready):
        gap = now - self.route.last_at
        if gap > ROUTE_MAX_INTERVAL:
            raise RuntimeError('route exceeded its actual maximum decision gap')
        if ready and gap >= ROUTE_MIN_INTERVAL:
            self.route_retries = 0
            return True
        self.route_retries += 1
        self.route_total_retries += 1
        if self.route_retries > MAX_ROUTE_RETRIES or self.route_total_retries > MAX_ROUTE_TOTAL_RETRIES:
            raise RuntimeError('bounded native route observation retries exhausted')
        self.next_delay = 0.1
        self.emit('route_wait', observed_at=now, previous_decision_at=self.route.last_at,
                  decision_gap_seconds=gap, world_ready=ready, retry_index=self.route_retries,
                  total_retries=self.route_total_retries, next_delay_seconds=self.next_delay,
                  command_issued=False)
        return False

    def advance(self):
        self.next_delay = 1.0
        if self.sampler is not None and self.sampler.error is not None:
            raise RuntimeError('passive sampler failed: ' + self.sampler.error)
        if self.complete:
            return True
        self.advances += 1
        self.ride_advances += 1
        if self.advances > MAX_ADVANCES or self.ride_advances > MAX_RIDE_ADVANCES:
            raise RuntimeError('native drive/return observation budget exhausted')
        now = probe._number(self.clock(), 0, 1e10, 'observation time')
        if self.last_time is not None and now <= self.last_time:
            raise RuntimeError('strictly increasing diagnostic observation clock required')
        previous_time, self.last_time = self.last_time, now
        if self.phase in ('return_hold', 'return_png') and now - previous_time > MAX_GAP:
            raise RuntimeError('returned native Hangar sample gap exceeded')
        self.drain()
        context = self.native.context()
        if not context['native_connected']:
            raise RuntimeError('native drive disconnected instead of warm return')
        if self.phase == 'between_rides':
            if not self.native.hangar_ready():
                raise RuntimeError('native returned Hangar lost before the next original fight')
            self._account(self.native.account())
            self._next_ride()
            return False
        if self.phase in ('initial', 'selecting'):
            if not self.native.hangar_ready():
                return False
            account = self.native.account()
            if account['selected_inventory_id'] != 1:
                if self.initial is not None:
                    raise RuntimeError('selected vehicle changed between completed native rides')
                if self.selected:
                    return False
                self.selected = True
                self.native.select_ms1()
                self.phase = 'selecting'
                self.emit('selection', inventory_id=1, origin='original_TankCarousel.vehicleChange')
                return False
            self._account(account)
            if self.initial is None:
                self.initial = account
            self.emit('account', moment='before', observed_at=now, snapshot=account)
            button = self.native.button_state()
            self.emit('button', observed_at=now, **button)
            self.phase = 'waiting_world'
            self.action('fight', now, button['owner_id'])
            self.fight_at = self.proofs['fight']['returned']['noted_at']
            return False
        if self.phase in ('waiting_return', 'return_hold', 'return_png'):
            self.emit('return_state', observed_at=now, context=context, hangar_ready=self.native.hangar_ready())
            if not self.native.hangar_ready():
                if self.phase != 'waiting_return':
                    raise RuntimeError('native returned Hangar readiness was lost')
                return False
            account = self.native.account()
            self._account(account)
            for kind, method, offset in (('avatar', 'onLeaveWorld', 948), ('avatar', 'onBecomeNonPlayer', 193),
                                         ('vehicle', 'stopVisual', 177), ('vehicle', 'onLeaveWorld', 48)):
                matches = [p['returned'] for p in self.pairs if p['returned']['kind'] == kind
                           and p['returned']['method'] == method and p['returned']['offset'] == offset]
                if len(matches) != 1:
                    raise RuntimeError('warm Hangar lacks exact original world teardown')
            self.emit('account', moment='after', observed_at=now, snapshot=account)
            if self.phase == 'waiting_return':
                self.phase, self.stable_since = 'return_hold', now
            elif self.phase == 'return_hold' and now - self.stable_since >= HOLD_SECONDS:
                self.capture(self.screen_names[2], now)
                self.phase = 'return_png'
            elif self.phase == 'return_png' and self.receipt(now):
                return self._complete_ride(now)
            return False
        if self.moving and now - self.command_at >= MAX_ACTION_SECONDS:
            raise RuntimeError('original movement made insufficient bounded progress')
        if not context['player_is_original_avatar']:
            if self.phase != 'waiting_world':
                raise RuntimeError('native Avatar disappeared before explicit return')
            if not context['player_is_original_account'] and context.get('player_present'):
                raise RuntimeError('unexpected native player class while awaiting arena')
            self.emit('waiting_world', observed_at=now, context=context,
                      avatar_getters='NOT_RUN', queue_acceptance='NOT_RUN',
                      fight_returned_at=self.fight_at)
            if (context['player_is_original_account']
                    and now - self.fight_at >= MAX_PREQUEUE_ACCOUNT_SECONDS):
                raise RuntimeError('native Account remains after original fight for thirty seconds')
            return False
        state, motion, attached = self.native.world(), self.native.motion(), self.native.binding()
        try:
            ready = self._world_ready(context, state, motion, attached)
        except Exception as error:
            # Preserve this actual iteration, not the last incomplete world.
            # Native getters already bound these primitive projections.
            self.emit('state_rejected', observed_at=now, context=context, vehicle=state,
                      motion=motion, binding=attached, geometry=self.geometry, world_ready=False,
                      error_type=type(error).__name__, detail=str(error)[:512])
            raise
        self.emit('state', observed_at=now, context=context, vehicle=state, motion=motion,
                  binding=attached, world_ready=ready, geometry=self.geometry)
        if not ready:
            if self.phase == 'route_active':
                self._route_due(now, False)
            if self.last_world is not None and now - self.last_world > MAX_GAP:
                raise RuntimeError('actual native world/provider readiness was lost')
            if self.last_world is not None:
                self.next_delay = 0.1
            return False
        if self.last_world is not None and now - self.last_world > MAX_GAP:
            raise RuntimeError('continuous native world sample gap exceeded')
        self.last_world = now
        position, axis, heading = _vector(motion['own_matrix_position']), _vector(motion['forward_axis']), motion['heading']
        if not self.ground_done:
            self.emit('ground', observed_at=now, **self.native.ground(self.map_id, context))
            self.ground_done = True
        if self.phase == 'waiting_world':
            self.phase, self.anchor, self.stable_since = 'baseline', position, now
        elif self.phase == 'baseline' and self._hold(motion, now):
            self.capture(self.screen_names[0], now)
            self.phase = 'entry_png'
        elif self.phase == 'entry_png' and self.receipt(now):
            if self.map_id == 1 and not self.route_done:
                self.route = _RoutePlan(position, heading, now)
                self.phase = 'route_active'
                self.emit('route_begin', observed_at=now, plan_sha256=ROUTE_PLAN_SHA256,
                          target_xz=[ROUTE_TARGET[0], ROUTE_TARGET[2]], input_assigned=False,
                          route_policy_version=ROUTE_POLICY_VERSION,
                          speed_source='original_WGVehicleFilter.speedInfo[0]',
                          offline_raw_speed_equivalence='NOT_CLAIMED')
                self._route_step(motion, attached, now)
            else:
                self._start_basic_drive(position, axis, now)
        elif self.phase == 'route_active':
            if self._route_due(now, True):
                self._route_step(motion, attached, now)
        elif self.phase == 'route_hold' and self._hold(motion, now) and now - self.stable_since >= 3.0:
            self.emit('hold', kind='route_stop', began_at=self.stable_since, observed_at=now, position=position)
            self.origin, self.axis = position, axis
            self.action('route_backoff', now, self.avatar_owner)
            self.phase = 'route_backoff'
        elif self.phase == 'route_backoff' and -_along(position, self.origin, self.axis) >= ROUTE_BACKOFF_METRES:
            self.emit('progress', kind='route_backoff', metres=-_along(position, self.origin, self.axis), observed_at=now)
            self.action('route_backoff_stop', now, self.avatar_owner)
            self.phase, self.anchor, self.stable_since = 'route_backoff_hold', position, now
        elif self.phase == 'route_backoff_hold' and self._hold(motion, now):
            self.emit('hold', kind='route_backoff_stop', began_at=self.stable_since, observed_at=now, position=position)
            self.route_done = True
            self._start_basic_drive(position, axis, now)
        elif self.phase == 'forward' and _along(position, self.origin, self.axis) >= FORWARD_METRES:
            self.turn_heading = heading
            self.emit('progress', kind='forward', metres=_along(position, self.origin, self.axis), observed_at=now)
            self.action('turn', now, self.avatar_owner)
            self.phase = 'turn'
        elif self.phase == 'turn' and abs(_heading_delta(heading, self.turn_heading)) >= TURN_RADIANS:
            self.emit('progress', kind='turn', radians=_heading_delta(heading, self.turn_heading), observed_at=now)
            self.action('stop_turn', now, self.avatar_owner)
            self.phase, self.anchor, self.stable_since = 'hold_turn', position, now
        elif self.phase == 'hold_turn' and self._hold(motion, now):
            self.emit('hold', kind='turn_stop', began_at=self.stable_since, observed_at=now, position=position)
            self.origin, self.axis = position, axis
            self.action('reverse', now, self.avatar_owner)
            self.phase = 'reverse'
        elif self.phase == 'reverse' and -_along(position, self.origin, self.axis) >= REVERSE_METRES:
            self.emit('progress', kind='reverse', metres=-_along(position, self.origin, self.axis), observed_at=now)
            self.action('stop_reverse', now, self.avatar_owner)
            self.phase, self.anchor, self.stable_since = 'hold_reverse', position, now
        elif self.phase == 'hold_reverse' and self._hold(motion, now):
            self.emit('hold', kind='reverse_stop', began_at=self.stable_since, observed_at=now, position=position)
            self.capture(self.screen_names[1], now)
            self.phase = 'driven_png'
        elif self.phase == 'driven_png' and self.receipt(now):
            self.phase = 'waiting_return'
            self.action('leave', now, self.avatar_owner)
        return False

    def emergency_stop(self, require_proof=True):
        if not self.moving:
            return
        context = self.native.context()
        if not context['player_is_original_avatar'] or context['player_owner_id'] != self.avatar_owner:
            self.emit('emergency_stop', outcome='NOT_RUN', reason='owned_avatar_no_longer_present')
            return
        # A failing evidence writer must not prevent the original stop attempt.
        # Keep passive intent attribution, but invoke before any further writes.
        self.intent = 'error_stop'
        try:
            self.native.move(0, False, self.avatar_owner)
            self.moving = False
        finally:
            self.intent = None
        if require_proof:
            self.drain()
            pair = self.proofs.get('error_stop')
            if pair is None or pair['returned']['owner_id'] != self.avatar_owner:
                raise RuntimeError('emergency stop lacks original callback proof')
            self.emit('emergency_stop', outcome='ORIGINAL_METHOD_RETURNED', callback_proof='OBSERVED')
        else:
            self.emit('emergency_stop', outcome='ORIGINAL_METHOD_RETURNED', callback_proof='NOT_RUN')



class _BoundaryScenario(_Scenario):
    diagnostic_mode = 'boundary_only'

    def __init__(self, record, settings, native=None, clock=None):
        self.record, self.clock = record, _now if clock is None else clock
        self.native = _Native(settings) if native is None else native
        self.phase, self.advances, self.sequence = 'initial', 0, 0
        self.ride_index, self.ride_advances = 1, 0
        self.completed_rides, self.maps_seen, self.spaces_seen, self.arenas_seen = [], set(), set(), set()
        self.space_id = self.arena_id = None
        self.boundary = None
        self.boundary_done = False
        self.hold_phase = None
        self.boundary_retries = self.boundary_total_retries = 0
        self.boundary_commands, self.commands = [], dict(BOUNDARY_COMMANDS)
        self.all_screenshots = []
        self.screen_names = BOUNDARY_SCREENSHOTS[:3]
        self.active, self.complete, self.moving = True, False, False
        self.last_time = self.last_world = self.stable_since = self.anchor = None
        self.hold_phase = None
        self.avatar_owner = self.vehicle_owner = self.initial = self.map_id = None
        self.geometry = self.latest_update = self.latest_bound = None
        self.return_geometry = self.pending_return_geometry = None
        self.intent = self.note_error = self.png = self.command_at = None
        self.fight_at = None
        self.next_delay = 1.0
        self.sampler = None
        self.sampler_count = self.total_samples = 0
        self.sample_last_update = self.sample_last_deferred = None
        self.notes, self.open_calls, self.seen, self.pairs = [], {}, set(), []
        self.proofs, self.screenshots = {}, []
        self.selected = self.ground_done = False
        self.sources = self.native.initialize()
        self.emit('armed', sources=self.sources, maps=dict((str(k), v) for k, v in MAPS.items()),
                  max_advances=MAX_ADVANCES, maximum_action_seconds=MAX_ACTION_SECONDS,
                  max_rides=MAX_RIDES, max_ride_advances=MAX_RIDE_ADVANCES,
                  boundary_plan_sha256=BOUNDARY_PLAN_SHA256,
                  maximum_boundary_forward_seconds=BOUNDARY_MAX_SECONDS,
                  boundary_feedback_budget=BOUNDARY_MAX_STEPS,
                  boundary_interval_bounds=[BOUNDARY_MIN_INTERVAL, BOUNDARY_MAX_INTERVAL],
                  boundary_stall_seconds=BOUNDARY_STALL_SECONDS,
                  boundary_stop_hold_seconds=BOUNDARY_STOP_HOLD_SECONDS,
                  boundary_backoff_metres=BOUNDARY_BACKOFF_METRES,
                  maximum_prequeue_account_seconds=MAX_PREQUEUE_ACCOUNT_SECONDS,
                  minimum_hold_seconds=HOLD_SECONDS, hold_tolerance_metres=HOLD_TOLERANCE,
                  max_samplers=0, max_process_samples=0, sampler_window='NOT_RUN_BOUNDARY_ONLY',
                  no_fully_airborne_gate='REQUIRES_ALL_WORKER_60HZ_MASKS_NONZERO',
                  native_contact_count_equivalence='NOT_CLAIMED',
                  physical_input=False, services_owner='map_drive_client', full_card_acceptance='NOT_RUN')

    def _complete_ride(self, now):
        required = set(('fight', 'leave'))
        if self.boundary is not None:
            required.update(self.boundary_commands)
            required.update(('boundary_stop', 'boundary_backoff', 'boundary_backoff_stop'))
            if not self.boundary_done:
                raise RuntimeError('Prohorovka boundary/backoff remains incomplete')
        if self.open_calls or self.notes or self.moving or set(self.proofs) != required:
            raise RuntimeError('one exact complete original action/lifecycle chain per ride required')
        if len(self.screenshots) != 3 or [r['basename'] for r in self.screenshots] != list(self.screen_names):
            raise RuntimeError('each complete ride needs its own three native PNGs')
        if self.space_id in self.spaces_seen or self.arena_id in self.arenas_seen:
            raise RuntimeError('completed native world identity reused')
        if self.sampler is not None or self.sampler_count != 0 or self.total_samples != 0:
            raise RuntimeError('boundary-only diagnostic must not claim basic-drive frame samples')
        self.maps_seen.add(self.map_id)
        self.spaces_seen.add(self.space_id)
        self.arenas_seen.add(self.arena_id)
        summary = dict(ride_index=self.ride_index, map_id=self.map_id, space_id=self.space_id,
                       arena_unique_id=self.arena_id, fight_at=self.fight_at, returned_at=now,
                       action_count=len(self.proofs), boundary_observed=self.boundary is not None,
                       role='boundary' if self.boundary is not None else 'random_map_skipped',
                       sampler_index=None, sample_count=0)
        self.completed_rides.append(summary)
        self.emit('ride_complete', observed_at=now, summary=summary, screenshots=self.screenshots,
                  action_call_ids=dict((k, v['returned']['call_id']) for k, v in self.proofs.items()),
                  account_invariant=True, completed_rides=len(self.completed_rides),
                  random_maps_seen=sorted(self.maps_seen))
        if self.map_id == 4 and self.boundary_done:
            self.phase, self.complete = 'complete', True
            self.emit('complete', observed_at=now, rides=self.completed_rides, screenshots=self.all_screenshots,
                      account_invariant=True, native_rides=len(self.completed_rides),
                      boundary_observed=True, original_boundary_commands_observed=True,
                      basic_drive_acceptance='NOT_RUN_IN_BOUNDARY_MODE_REQUIRES_SEPARATE_PHASE2_DRIVE',
                      sampler_count=self.sampler_count, process_sample_count=self.total_samples,
                      collision_acceptance='NOT_RUN_REQUIRES_INDEPENDENT_SERVER_BOUNDARY_AND_ALL_WORKER_CONTACTS',
                      physical_input_acceptance='NOT_RUN')
            return True
        if self.ride_index >= MAX_RIDES:
            raise RuntimeError('bounded random-map attempts exhausted without original Prohorovka')
        self.phase = 'between_rides'
        return False

    def _next_ride(self):
        if self.notes or self.open_calls or self.png is not None or self.moving:
            raise RuntimeError('previous ride retains callbacks, PNG, or movement ownership')
        if self.sampler is not None or self.ride_index >= MAX_RIDES:
            raise RuntimeError('no sampler resources may cross a bounded boundary-only reentry')
        self.ride_index += 1
        self.ride_advances = 0
        self.phase = 'initial'
        self.last_world = self.stable_since = self.anchor = None
        self.hold_phase = None
        self.avatar_owner = self.vehicle_owner = self.map_id = None
        self.geometry = self.latest_update = self.latest_bound = None
        self.return_geometry = self.pending_return_geometry = None
        self.intent = self.png = self.command_at = self.fight_at = None
        self.sampler = None
        self.sample_last_update = self.sample_last_deferred = None
        self.space_id = self.arena_id = None
        self.pairs, self.proofs, self.screenshots = [], {}, []
        self.selected = self.ground_done = False
        self.commands, self.boundary_commands, self.boundary = dict(BOUNDARY_COMMANDS), [], None
        self.screen_names = BOUNDARY_SCREENSHOTS[(self.ride_index - 1) * 3:self.ride_index * 3]
        self.emit('next_ride', previous_world_references_released=True, ordinary_services_reinitialized=False,
                  process_callback_sequence=self.sequence, seen_maps=sorted(self.maps_seen),
                  previous_sampler_stopped=False, sampler_ownership='NOT_STARTED_BOUNDARY_ONLY', process_samplers=self.sampler_count,
                  process_sample_count=self.total_samples)

    def _boundary_step(self, motion, now):
        row = self.boundary.sample(_vector(motion['own_matrix_position']), motion['speed_info'][0],
                                   motion['tilt_radians'], now)
        self.emit('boundary_sample', speed_source='original_WGVehicleFilter.speedInfo[0]',
                  last_server_speeds_used_for_control=False, **row)
        if row['stop_candidate']:
            self.action('boundary_stop', now, self.avatar_owner)
            self.phase, self.anchor, self.stable_since = 'boundary_hold', None, None
            return
        name = 'boundary_%03d' % row['sample_index']
        self.commands[name] = (1, True)
        self.boundary_commands.append(name)
        self.action(name, now, self.avatar_owner)

    def _boundary_due(self, now, ready):
        if now-self.boundary.started_at >= BOUNDARY_MAX_SECONDS:
            raise RuntimeError('bounded boundary forward time exhausted')
        gap = now-self.boundary.last_at
        if gap > BOUNDARY_MAX_INTERVAL:
            raise RuntimeError('boundary exceeded actual maximum renewal gap')
        if ready and gap >= BOUNDARY_MIN_INTERVAL:
            self.boundary_retries = 0
            return True
        self.boundary_retries += 1
        self.boundary_total_retries += 1
        if self.boundary_retries > BOUNDARY_MAX_RETRIES or self.boundary_total_retries > BOUNDARY_MAX_TOTAL_RETRIES:
            raise RuntimeError('bounded native boundary observation retries exhausted')
        self.next_delay = 0.1
        self.emit('boundary_wait', observed_at=now, previous_decision_at=self.boundary.last_at,
                  decision_gap_seconds=gap, world_ready=ready, retry_index=self.boundary_retries,
                  total_retries=self.boundary_total_retries, command_issued=False,
                  next_delay_seconds=self.next_delay)
        return False

    def advance(self):
        self.next_delay = 1.0
        if self.sampler is not None and self.sampler.error is not None:
            raise RuntimeError('passive sampler failed: ' + self.sampler.error)
        if self.complete:
            return True
        self.advances += 1
        self.ride_advances += 1
        if self.advances > MAX_ADVANCES or self.ride_advances > MAX_RIDE_ADVANCES:
            raise RuntimeError('native drive/return observation budget exhausted')
        now = probe._number(self.clock(), 0, 1e10, 'observation time')
        if self.last_time is not None and now <= self.last_time:
            raise RuntimeError('strictly increasing diagnostic observation clock required')
        previous_time, self.last_time = self.last_time, now
        if self.phase in ('return_hold', 'return_png') and now - previous_time > MAX_GAP:
            raise RuntimeError('returned native Hangar sample gap exceeded')
        self.drain()
        context = self.native.context()
        if not context['native_connected']:
            raise RuntimeError('native drive disconnected instead of warm return')
        if self.phase == 'between_rides':
            if not self.native.hangar_ready():
                raise RuntimeError('native returned Hangar lost before the next original fight')
            self._account(self.native.account())
            self._next_ride()
            return False
        if self.phase in ('initial', 'selecting'):
            if not self.native.hangar_ready():
                return False
            account = self.native.account()
            if account['selected_inventory_id'] != 1:
                if self.initial is not None:
                    raise RuntimeError('selected vehicle changed between completed native rides')
                if self.selected:
                    return False
                self.selected = True
                self.native.select_ms1()
                self.phase = 'selecting'
                self.emit('selection', inventory_id=1, origin='original_TankCarousel.vehicleChange')
                return False
            self._account(account)
            if self.initial is None:
                self.initial = account
            self.emit('account', moment='before', observed_at=now, snapshot=account)
            button = self.native.button_state()
            self.emit('button', observed_at=now, **button)
            self.phase = 'waiting_world'
            self.action('fight', now, button['owner_id'])
            self.fight_at = self.proofs['fight']['returned']['noted_at']
            return False
        if self.phase in ('waiting_return', 'return_hold', 'return_png'):
            self.emit('return_state', observed_at=now, context=context, hangar_ready=self.native.hangar_ready())
            if not self.native.hangar_ready():
                if self.phase != 'waiting_return':
                    raise RuntimeError('native returned Hangar readiness was lost')
                return False
            account = self.native.account()
            self._account(account)
            for kind, method, offset in (('avatar', 'onLeaveWorld', 948), ('avatar', 'onBecomeNonPlayer', 193),
                                         ('vehicle', 'stopVisual', 177), ('vehicle', 'onLeaveWorld', 48)):
                matches = [p['returned'] for p in self.pairs if p['returned']['kind'] == kind
                           and p['returned']['method'] == method and p['returned']['offset'] == offset]
                if len(matches) != 1:
                    raise RuntimeError('warm Hangar lacks exact original world teardown')
            self.emit('account', moment='after', observed_at=now, snapshot=account)
            if self.phase == 'waiting_return':
                self.phase, self.stable_since = 'return_hold', now
            elif self.phase == 'return_hold' and now - self.stable_since >= HOLD_SECONDS:
                self.capture(self.screen_names[2], now)
                self.phase = 'return_png'
            elif self.phase == 'return_png' and self.receipt(now):
                return self._complete_ride(now)
            return False
        if self.moving and self.phase != 'boundary_active' and now - self.command_at >= MAX_ACTION_SECONDS:
            raise RuntimeError('original movement made insufficient bounded progress')
        if not context['player_is_original_avatar']:
            if self.phase != 'waiting_world':
                raise RuntimeError('native Avatar disappeared before explicit return')
            if not context['player_is_original_account'] and context.get('player_present'):
                raise RuntimeError('unexpected native player class while awaiting arena')
            self.emit('waiting_world', observed_at=now, context=context,
                      avatar_getters='NOT_RUN', queue_acceptance='NOT_RUN',
                      fight_returned_at=self.fight_at)
            if (context['player_is_original_account']
                    and now - self.fight_at >= MAX_PREQUEUE_ACCOUNT_SECONDS):
                raise RuntimeError('native Account remains after original fight for thirty seconds')
            return False
        state, motion, attached = self.native.world(), self.native.motion(), self.native.binding()
        try:
            ready = self._world_ready(context, state, motion, attached)
        except Exception as error:
            # Preserve this actual iteration, not the last incomplete world.
            # Native getters already bound these primitive projections.
            self.emit('state_rejected', observed_at=now, context=context, vehicle=state,
                      motion=motion, binding=attached, geometry=self.geometry, world_ready=False,
                      error_type=type(error).__name__, detail=str(error)[:512])
            raise
        self.emit('state', observed_at=now, context=context, vehicle=state, motion=motion,
                  binding=attached, world_ready=ready, geometry=self.geometry)
        if not ready:
            if self.phase == 'boundary_active':
                self._boundary_due(now, False)
            if self.last_world is not None and now - self.last_world > MAX_GAP:
                raise RuntimeError('actual native world/provider readiness was lost')
            if self.last_world is not None:
                self.next_delay = 0.1
            return False
        if self.last_world is not None and now - self.last_world > MAX_GAP:
            raise RuntimeError('continuous native world sample gap exceeded')
        self.last_world = now
        if probe._number(motion['tilt_radians'], 0, math.pi, 'native tilt') > BOUNDARY_MAX_TILT:
            raise RuntimeError('native boundary diagnostic tilt exceeds thirty degrees')
        position, axis, heading = _vector(motion['own_matrix_position']), _vector(motion['forward_axis']), motion['heading']
        if not self.ground_done:
            self.emit('ground', observed_at=now, **self.native.ground(self.map_id, context))
            self.ground_done = True
        if self.phase == 'waiting_world':
            self.phase, self.anchor, self.stable_since = 'baseline', position, now
        elif self.phase == 'baseline' and self._hold(motion, now):
            self.capture(self.screen_names[0], now)
            self.phase = 'entry_png'
        elif self.phase == 'entry_png' and self.receipt(now):
            if self.map_id == 4:
                self.boundary = _BoundaryPlan(position, heading, now)
                self.phase = 'boundary_active'
                self.emit('boundary_begin', observed_at=now, plan_sha256=BOUNDARY_PLAN_SHA256,
                          position=position, maximum_forward_seconds=BOUNDARY_MAX_SECONDS,
                          desired_map_selected_by='SERVER_RANDOM', native_state_assigned=False)
                self._boundary_step(motion, now)
            else:
                self.emit('boundary_map_skipped', observed_at=now, actual_map=self.map_id,
                          movement_commands_issued=False, desired_map_selected_by='SERVER_RANDOM')
                self.capture(self.screen_names[1], now)
                self.phase = 'leg_end_png'
        elif self.phase == 'boundary_active':
            if self._boundary_due(now, True):
                self._boundary_step(motion, now)
        elif self.phase == 'boundary_hold' and self._hold(motion, now) and now-self.stable_since >= BOUNDARY_STOP_HOLD_SECONDS:
            self.emit('hold', kind='boundary_stop', began_at=self.stable_since, observed_at=now,
                      position=position, interval_start='FIRST_VALID_LOW_SPEED_SAMPLE')
            self.origin, self.axis = position, axis
            self.action('boundary_backoff', now, self.avatar_owner)
            self.phase = 'boundary_backoff'
        elif self.phase == 'boundary_backoff' and -_along(position, self.origin, self.axis) >= BOUNDARY_BACKOFF_METRES:
            self.emit('progress', kind='boundary_backoff', metres=-_along(position, self.origin, self.axis), observed_at=now)
            self.action('boundary_backoff_stop', now, self.avatar_owner)
            self.phase, self.anchor, self.stable_since = 'boundary_backoff_hold', None, None
        elif self.phase == 'boundary_backoff_hold' and self._hold(motion, now):
            self.emit('hold', kind='boundary_backoff_stop', began_at=self.stable_since, observed_at=now,
                      position=position, interval_start='FIRST_VALID_LOW_SPEED_SAMPLE')
            self.boundary_done = True
            self.emit('boundary_observed', observed_at=now,
                      boundary_physics_acceptance='NOT_RUN_REQUIRES_INDEPENDENT_WORKER_WALL_GEOMETRY',
                      all_worker_ticks_contact_acceptance='NOT_RUN_REQUIRES_INDEPENDENT_60HZ_MASKS')
            self.capture(self.screen_names[1], now)
            self.phase = 'leg_end_png'
        elif self.phase == 'leg_end_png' and self.receipt(now):
            self.phase = 'waiting_return'
            self.action('leave', now, self.avatar_owner)
        return False


def checked_mode(mode):
    if type(mode) not in probe.string_types or mode not in MODES:
        raise ValueError('explicit diagnostic mode must be phase2_drive or boundary_only')
    return mode


def arm(record, settings, mode='phase2_drive'):
    global _run, _attempted
    if _attempted or not callable(record):
        raise RuntimeError('one explicit acceptance arm with recorder required')
    mode = checked_mode(mode)
    _attempted = True
    cls = _Scenario if mode == 'phase2_drive' else _BoundaryScenario
    _run = cls(record, settings)


def _note(kind, phase, method, line, offset, call_id, owner_id, data):
    if _run is None or _closing:
        return False
    return _run.note(kind, phase, method, line, offset, call_id, owner_id, data)


def note_avatar_call(phase, method, line, offset, call_id, owner_id, entity_id, space_id):
    if method not in ENTITY_METHODS['avatar']:
        return False
    return _note('avatar', phase, method, line, offset, call_id, owner_id, dict(entity_id=entity_id, space_id=space_id))


def note_vehicle_call(phase, method, line, offset, call_id, owner_id, entity_id, space_id):
    return _note('vehicle', phase, method, line, offset, call_id, owner_id, dict(entity_id=entity_id, space_id=space_id))


def note_geometry_mapped(space_id, path):
    return False if _run is None or _closing else _run.note_geometry(space_id, path)


def note_movement_call(phase, method, line, offset, call_id, owner_id, data):
    return _note('movement', phase, method, line, offset, call_id, owner_id, data)


def note_map_drive_call(phase, method, line, offset, call_id, owner_id, data):
    return _note('binding', phase, method, line, offset, call_id, owner_id, data)


def note_action_call(phase, method, line, offset, call_id, owner_id, data):
    return _note('action', phase, method, line, offset, call_id, owner_id, data)


def advance(record):
    if _run is None or _closing:
        return False
    if record is not _run.record:
        raise RuntimeError('acceptance recorder changed')
    try:
        return _run.advance()
    except Exception as error:
        logging_error = None
        try:
            if _run.sampler is not None:
                _run.sampler.stop('diagnostic_error')
            _run.emit('error', error_type=type(error).__name__, detail=str(error)[:512])
        except Exception as record_error:
            logging_error = type(record_error).__name__
        try:
            _run.emergency_stop()
        except Exception as stop_error:
            raise RuntimeError('acceptance failed; stop/proof failed: ' + type(error).__name__ + ', ' + type(stop_error).__name__)
        if logging_error is not None:
            raise RuntimeError('acceptance and error evidence write failed: ' + type(error).__name__ + ', ' + logging_error)
        raise


def next_observation_delay():
    """Pure explicit-diagnostic scheduler hint; never owns an engine callback."""
    if _run is None or _closing or not _run.active or _run.complete:
        return 1.0
    return _run.next_delay


def fini(record):
    """Release only diagnostic ownership. Root must still run ordinary cleanup."""
    global _closing
    if _closing:
        return
    _closing = True
    if _run is not None:
        try:
            try:
                if _run.sampler is not None:
                    _run.sampler.stop('diagnostic_fini')
            finally:
                _run.emergency_stop(require_proof=False)
                _run.drain()
        finally:
            _run.active = False
            _run.notes = []
            _run.emit('diagnostic_fini', ordinary_service_cleanup_required=True, completed=_run.complete)
