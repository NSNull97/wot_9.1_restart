# -*- coding: utf-8 -*-
"""Opt-in #717 attachment/provider checkpoint, not a complete driving mode.

Only the audited original moveVehicle start/stop pair is invoked. Attachment,
clock, body/filter/matrix values and updateOwnVehiclePosition belong to the
engine/server. The frozen movement module supplies unchanged lifecycle and
command validation; this module has independent state, callbacks and filenames.
"""
import hashlib
import os

import arena_bootstrap
import arena_entry_probe as probe
import arena_movement_scenario as movement
import arena_vehicle_scenario as vehicle
from ms1_crew_scenario import _Native as ScreenshotNative, _now

VERSION = 2
MAX_ADVANCES, MAX_GAP, MAX_PNG_ADVANCES = 239, 3.0, 15
MAX_BINDING_PENDING, MAX_BINDING_NOTES = 128, 2048
MIN_BASELINE_SECONDS, MIN_HOLD_SECONDS = 2.0, 2.0
MAX_COMMAND_SECONDS = 8.0
ORIGIN, TARGET, XZ_TOLERANCE = movement.ORIGIN, movement.TARGET, 0.02
PROVIDER_TOLERANCE = 0.002
SCREENSHOTS = ('map_drive_before', 'map_drive_after')
METHODS = (
    ('updateOwnVehiclePosition', 'updateOwnVehiclePosition', 1445, 5,
     'e3d0da962d39de10f9154c530af3938ee2273ffce03d068836f70e0c57541453'),
    ('_PlayerAvatar__setOwnVehicleMatrixCallback', '__setOwnVehicleMatrixCallback', 2951, 1,
     'c3bdf1ce42242b74ef4afeff919b474e68ed41663c5e076a62f7d336f8447d8b'),
)
RETURNS = {'updateOwnVehiclePosition': (1445, (198,)),
           '__setOwnVehicleMatrixCallback': (2951, (151, 179))}
SOURCE_HASHES = (
    ('res/scripts/client/Avatar.pyc', 'c13cd58a4c5d766dfd3c5f47ae7be50c962aee6c7f8cf25b4341322381f21e0e'),
    ('res/scripts/client/AvatarPositionControl.pyc', '7101af94b5f075bb3eed8dd27fbac65b62b2841cd01302a5e9e6daebf5d69882'),
    ('res/scripts/common/items/vehicles.pyc', '805240e4b59d8a75950dbb97b41c17867606e7e96d7ff0c8d7b05312b83ae8b6'),
    ('res/scripts/common/physics_shared.pyc', '487e2453c8e4540a9921353ebe651e833fd4145a1cc0623d70927cbb57863a77'),
    ('res/scripts/item_defs/vehicles/ussr/ms-1.xml', 'a494bf04d29da7d066fd6923dbb75a79b947559a52405298c494a943c4b0c535'),
    ('res/scripts/item_defs/vehicles/ussr/components/engines.xml', '196e52561bd04d2d4e5838442f62704456f4b901627248e04b2c9bd37d32f60d'),
    ('res/scripts/item_defs/vehicles/ussr/components/fueltanks.xml', '1f182b76fceeabf2ff1d828cc5b2aea37b94585f78488bd2dd7c195f8862b013'),
    ('res/scripts/item_defs/vehicles/ussr/components/radios.xml', '099292b8b5f5e250b2cd506419d18620f4f2504950776b54983bc303b2ca201a'),
    ('res/scripts/item_defs/vehicles/ussr/components/guns.xml', '889fe1564987566478c474ddfef21cbc7742d23bebd19f6a200c59bfafd7d87b'),
)
RAY_PLAN_SHA256 = '2f6eb519a01453360d7de2665640d8289f1ac48b97c61149b6627d80f7cd5a4b'
# Fixed original-derived data-team queries. Expected heights deliberately do
# not enter this module or the native completion condition.
GROUND_RAYS = (
    ('seed', -58.499908447265625, -445.81304931640625),
    ('east5', -53.499908447265625, -445.81304931640625),
    ('west5', -63.499908447265625, -445.81304931640625),
    ('north5', -58.499908447265625, -440.81304931640625),
    ('south5', -58.499908447265625, -450.81304931640625),
    ('other_triangle', -57.79990768432617, -444.9130554199219),
    ('stone_top', -47.92145919799805, -496.2518005371094),
)
_run = _native = None
_arm_attempted = _closing = _finished_cleanup = False
_cleanup_errors = []


def _emit(record, event, **fields):
    fields['version'] = VERSION
    return probe._emit(record, event, fields)


def _routed(record):
    """Route only this instance's inherited events; never mutate frozen globals."""
    names = {'arena_vehicle_callback': 'map_drive_entity_callback',
             'arena_movement_callback': 'map_drive_movement_callback',
             'arena_movement_command': 'map_drive_command',
             'arena_movement_light': 'map_drive_light'}
    def write(event, **fields):
        return record(names.get(event, event), **fields)
    return write


def _audit_sources():
    root, rows = os.path.realpath(os.getcwd()), []
    for relative, expected in SOURCE_HASHES:
        path = os.path.join(root, *relative.split('/'))
        if (not os.path.realpath(path).startswith(root + os.sep) or os.path.islink(path)
                or not os.path.isfile(path) or not 1 <= os.path.getsize(path) <= 1048576):
            raise ValueError('bounded original binding source required')
        with open(path, 'rb') as stream:
            raw = stream.read(1048577)
        if len(raw) > 1048576 or hashlib.sha256(raw).hexdigest() != expected:
            raise ValueError('original binding source differs: ' + relative)
        rows.append(dict(relative_path=relative, bytes=len(raw), sha256=expected))
    return rows


def _bindings():
    import Avatar
    for contract in METHODS:
        probe._code_contract(getattr(Avatar.PlayerAvatar, contract[0]), contract, 'scripts/client/Avatar.py')


def _vector(value, count, label):
    if len(value) != count:
        raise ValueError('exact numeric vector length required: ' + label)
    return [probe._number(value[i], -1000000, 1000000, label) for i in range(count)]


def _position(value):
    if type(value) is not list:
        raise ValueError('primitive position list required')
    return _vector(value, 3, 'position')


def _near(value, target, axes=(0, 2), tolerance=XZ_TOLERANCE):
    return all(abs(value[i] - target[i]) <= tolerance for i in axes)


def _callback_data(method, data):
    if type(data) is not dict:
        raise ValueError('exact callback data dictionary required')
    if method == '__setOwnVehicleMatrixCallback':
        if data:
            raise ValueError('deferred binding callback has no public arguments')
        return {}
    if set(data) != set(('position', 'direction', 'speed', 'rspeed')):
        raise ValueError('exact original position callback arguments required')
    return dict(position=_position(data['position']), direction=_position(data['direction']),
                speed=probe._number(data['speed'], -1000, 1000, 'speed'),
                rspeed=probe._number(data['rspeed'], -1000, 1000, 'rspeed'))


def _ray_result(value):
    if value is None:
        return dict(status='MISS', point=None, normal=None, material=None,
                    opaque_vector=None, opaque_integers=None)
    if type(value) is not tuple or len(value) != 6:
        raise ValueError('original collision result must be None or a six-element tuple')
    return dict(status='HIT', point=_vector(value[0], 3, 'ray hit point'),
        normal=_vector(value[1], 3, 'ray hit normal'),
        material=probe._integer(value[2], -2147483648, 4294967295, 'ray material'),
        opaque_vector=_vector(value[3], 3, 'opaque collision vector'),
        opaque_integers=[probe._integer(value[i], -2147483648, 4294967295, 'opaque collision integer')
                         for i in (4, 5)])


class _Pixels(ScreenshotNative):
    def request(self, basename):
        import BigWorld
        if basename not in SCREENSHOTS or basename in self.requested:
            raise ValueError('unsupported or repeated map binding screenshot')
        names = self._entries()
        if any(not any(name.startswith(prefix + '_') and name.endswith('.png')
                       for prefix in self.requested) for name in names):
            raise ValueError('map binding screenshot directory contains an unowned file')
        if any(name.startswith(basename + '_') for name in names):
            raise ValueError('map binding screenshot must not overwrite a file')
        self.requested.add(basename)
        BigWorld.screenShot('png', basename)


class _Native(movement._Native):
    def __init__(self, record, settings):
        movement._Native.__init__(self, _routed(record), settings)
        self.pixels = _Pixels(settings)

    def initialize(self):
        self.map_drive_sources = _audit_sources()
        _bindings()
        movement._Native.initialize(self)

    def binding(self):
        """Actual native attachment, not getVehicleAttached's fallback lookup."""
        import Avatar
        import BigWorld
        import Math
        import Vehicle
        player, current = BigWorld.player(), BigWorld.entity(vehicle.VEHICLE_ID)
        if type(player) is not Avatar.PlayerAvatar or current is None or not current.isStarted:
            return {'present': False}
        if type(current) is not Vehicle.Vehicle:
            raise RuntimeError('exact original own Vehicle required for matrix observation')
        attached, provider, filt = player.vehicle, player.getOwnVehicleMatrix(), current.filter
        is_filter = type(filt) is BigWorld.WGVehicleFilter
        body = filt.bodyMatrix if is_filter else None
        target = provider.target
        return dict(present=True, owner_id=id(player), vehicle_owner_id=id(current),
            attached_vehicle_id=None if attached is None else probe._integer(attached.id, 1, 2147483647, 'attachment'),
            attached_owner_id=None if attached is None else id(attached),
            attached_is_own_vehicle=attached is current,
            filter_is_original_wg_vehicle=is_filter,
            # #717 getter6ae7a0 -> factory6a9f20 allocates a new Python-visible
            # matrix provider on every bodyMatrix read. Python identity is an
            # observation only; original callback151/STORE127 plus semantic
            # provider following and real displacement establish the binding.
            target_present=target is not None,
            target_python_identity_equal=body is not None and target is body,
            provider_owner_id=id(provider), target_owner_id=None if target is None else id(target),
            body_owner_id=None if body is None else id(body),
            avatar_position=probe._position(player.position, 'Avatar.position'),
            own_matrix_position=probe._position(Math.Matrix(provider).translation, 'own matrix'),
            body_matrix_position=None if body is None else probe._position(Math.Matrix(body).translation, 'body matrix'),
            target_position=None if target is None else probe._position(Math.Matrix(target).translation, 'target matrix'),
            last_server_speeds=_vector(player._PlayerAvatar__lastVehicleSpeeds, 2, 'last server speeds'))

    def physics(self):
        """Read already loaded descriptor/hit testers; never create physics objects."""
        import BigWorld
        import Vehicle
        from items import vehicles
        current = BigWorld.entity(vehicle.VEHICLE_ID)
        if type(current) is not Vehicle.Vehicle or not current.isStarted:
            raise RuntimeError('started original Vehicle required for descriptor physics export')
        desc = current.typeDescriptor
        if not arena_bootstrap._exact_instance(desc, vehicles.VehicleDescr):
            raise RuntimeError('original VehicleDescr required')
        physics = desc.physics
        scalars = ('weight', 'enginePower', 'specificFriction', 'minPlaneNormalY', 'trackCenterOffset',
                   'navmeshGirth', 'brakeForce', 'rotationSpeedLimit', 'rotationEnergy')
        values = dict((key, probe._number(physics[key], 0, 1e12, key)) for key in scalars)
        values.update(speedLimits=_vector(physics['speedLimits'], 2, 'speed limits'),
            terrainResistance=_vector(physics['terrainResistance'], 3, 'terrain resistance'),
            rotationIsAroundCenter=probe._boolean(physics['rotationIsAroundCenter'], 'rotation around center'))
        bounds = {}
        for part, section in (('chassis', desc.chassis), ('hull', desc.hull), ('turret', desc.turret)):
            bbox = section['hitTester'].bbox
            if len(bbox) != 3:
                raise ValueError('original hit tester bbox triple required')
            lo, hi = _vector(bbox[0], 3, part + ' bbox min'), _vector(bbox[1], 3, part + ' bbox max')
            if not all(lo[i] < hi[i] for i in range(3)):
                raise ValueError('nonempty native collision bounds required')
            bounds[part] = dict(minimum=lo, maximum=hi)
        return dict(vehicle_id=current.id, vehicle_owner_id=id(current), type_compact_descr=desc.type.compactDescr,
            compact_descr_sha256=vehicle._bytes_sha(desc.makeCompactDescr()), descriptor_owner_id=id(desc),
            physics=values, collision_bounds=bounds,
            top_right_carrying_point=_vector(desc.chassis['topRightCarryingPoint'], 2, 'carrying point'),
            hull_position=_vector(desc.chassis['hullPosition'], 3, 'hull position'),
            turret_position=_vector(desc.hull['turretPositions'][0], 3, 'turret position'),
            gun_position=_vector(desc.turret['gunPosition'], 3, 'gun position'),
            state_assigned=False, physics_created=False, historical_physics_acceptance='NOT_RUN')

    def ground_samples(self):
        import Avatar
        import BigWorld
        import Math
        player = BigWorld.player()
        if type(player) is not Avatar.PlayerAvatar or not player.inWorld or player.spaceID != 1:
            raise RuntimeError('actual native Karelia space required for ground queries')
        rows = []
        for name, x, z in GROUND_RAYS:
            start, end = [x, 200.0, z], [x, -50.0, z]
            result = BigWorld.wg_collideSegment(1, Math.Vector3(*start), Math.Vector3(*end), 18)
            rows.append(dict(sample_id=name, start=start, end=end, flags=18, result=_ray_result(result)))
        return dict(space_id=1, player_owner_id=id(player), geometry_path=probe.GEOMETRY_PATH,
            samples=rows, source_sample_plan_sha256=RAY_PLAN_SHA256, expected_heights_in_native_condition=False,
            spatial_mutation=False, comparison_acceptance='NOT_RUN')


class _Scenario(movement._Scenario):
    def __init__(self, record, native, clock=None):
        # Separate state; inherited methods only validate original lifecycle and
        # the authorized moveVehicle pair. No frozen module global is rewritten.
        self.record, self.native, self.clock = _routed(record), native, _now if clock is None else clock
        self.advances, self.sequence = 0, 0
        self.notes, self.open_calls, self.pairs, self.seen = [], {}, [], set()
        self.note_error = None
        self.active, self.complete, self.geometry = False, False, None
        self.avatar_owner = self.vehicle_owner = None
        self.ready_since = self.last_ready = self.last_time = self.last_server_time = None
        self.ready_samples, self.phase = 0, 'waiting_binding'
        self.movement_notes, self.movement_open, self.movement_pairs, self.movement_seen = [], {}, [], set()
        self.movement_error, self.movement_sequence = None, 0
        self.pending_png, self.png_advance, self.screenshots = None, None, []
        self.started_at = self.stopped_at = self.hold_since = None
        self.forward_attempted = self.stop_attempted = False
        self.forward_pair = self.stop_pair = None
        self.intent = None
        self.binding_notes, self.binding_open, self.binding_pairs, self.binding_seen = [], {}, [], set()
        self.binding_error, self.binding_sequence = None, 0
        self.latest_update = self.latest_bound = None
        self.physics_data = self.baseline_binding = None
        self.ground_data = None
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
        _emit(self.record, 'map_drive_armed', account=self.account, repository_owner_id=self.repository,
            expected_vehicle=self.expected, sources=native.sources, movement_sources=native.movement_sources,
            map_drive_sources=native.map_drive_sources, lab_origin=list(ORIGIN), lab_target=list(TARGET),
            xz_tolerance=XZ_TOLERANCE, provider_tolerance=PROVIDER_TOLERANCE,
            maximum_command_seconds=MAX_COMMAND_SECONDS, minimum_hold_seconds=MIN_HOLD_SECONDS,
            max_advances=MAX_ADVANCES, max_binding_notes=MAX_BINDING_NOTES,
            screenshot_basenames=list(SCREENSHOTS), clock_modified=False, entity_position_assigned=False,
            matrix_target_assigned=False, attachment_assigned=False, computer_input=False,
            full_drive_acceptance='NOT_RUN', native_entity_created_by_scenario=False)

    def note_binding(self, phase, method, line, offset, call_id, owner_id, data):
        if not self.active or type(method) not in probe.string_types or method not in RETURNS:
            return False
        try:
            if type(phase) not in probe.string_types or phase not in ('call', 'return'):
                raise ValueError('exact binding callback phase required')
            if len(self.binding_notes) >= MAX_BINDING_PENDING or self.binding_sequence >= MAX_BINDING_NOTES:
                raise ValueError('binding callback budget exhausted')
            row = dict(phase=phase, method=method, source_line=probe._integer(line, 1, 100000, 'line'),
                offset=probe._integer(offset, -1, 100000, 'offset'),
                call_id=probe._integer(call_id, 1, 2147483647, 'call ID'),
                owner_id=probe._integer(owner_id, 1, 0x7fffffffffffffff, 'owner ID'),
                data=_callback_data(method, data), noted_at=probe._number(self.clock(), 0, 1e10, 'note clock'))
            self.binding_sequence += 1
            row['sequence'] = self.binding_sequence
            self.binding_notes.append(row)
            return True
        except (ValueError, TypeError, UnicodeError) as error:
            if self.binding_error is None:
                self.binding_error = 'invalid passive binding note: ' + type(error).__name__
            return False

    def drain_binding(self):
        if self.binding_error:
            raise RuntimeError(self.binding_error)
        pending, self.binding_notes = self.binding_notes, []
        for note in pending:
            _emit(self.record, 'map_drive_binding_callback', **note)
            line, returns = RETURNS[note['method']]
            if (note['source_line'] != line or note['owner_id'] != self.avatar_owner
                    or note['offset'] not in ((-1,) if note['phase'] == 'call' else returns)):
                raise RuntimeError('original binding source/owner/offset differs')
            cid = note['call_id']
            if note['phase'] == 'call':
                if cid in self.binding_seen:
                    raise RuntimeError('duplicate binding callback call ID')
                self.binding_seen.add(cid)
                self.binding_open[cid] = note
                continue
            entry = self.binding_open.pop(cid, None)
            if entry is None or any(entry[key] != note[key] for key in ('method', 'owner_id', 'data')):
                raise RuntimeError('original binding return lacks its unchanged entry')
            pair = dict(entry=entry, returned=note)
            if note['method'] == 'updateOwnVehiclePosition':
                self.latest_update = pair
                self.latest_bound = None
            elif note['offset'] == 151:
                if self.latest_update is None or entry['sequence'] <= self.latest_update['returned']['sequence']:
                    raise RuntimeError('deferred binding success lacks prior original update')
                pair['update_call_id'] = self.latest_update['returned']['call_id']
                self.latest_bound = pair
            self.binding_pairs.append(pair)

    def binding_ready(self, value, motion):
        if not value.get('present'):
            return False
        if value['owner_id'] != self.avatar_owner or value['vehicle_owner_id'] != self.vehicle_owner:
            raise RuntimeError('binding observation belongs to another native owner')
        if value['attached_vehicle_id'] not in (None, vehicle.VEHICLE_ID):
            raise RuntimeError('Avatar attached to an unexpected native entity')
        if value['attached_vehicle_id'] is not None and value['attached_owner_id'] != self.vehicle_owner:
            raise RuntimeError('native attachment owner differs')
        if not (value['attached_is_own_vehicle'] is True and value['filter_is_original_wg_vehicle'] is True
                and value['target_present'] is True
                and self.latest_bound is not None and not self.binding_open):
            return False
        if not (vehicle._int(value['provider_owner_id'], 1) and vehicle._int(value['body_owner_id'], 1)
                and vehicle._int(value['target_owner_id'], 1)
                and type(value['target_python_identity_equal']) is bool):
            raise RuntimeError('bounded native provider wrapper identities required')
        own, body, target = [_position(value[key]) for key in
                             ('own_matrix_position', 'body_matrix_position', 'target_position')]
        # As in the measured Q checkpoint, server/native output Y is reported
        # separately. Repeated static-to-body adaptation is not evidence of a
        # historically correct suspension/vertical correction model.
        if (not _near(own, body)
                or not _near(target, body, (0, 1, 2), PROVIDER_TOLERANCE)
                or not _near(own, _position(motion['own_matrix_position']), (0, 1, 2), PROVIDER_TOLERANCE)):
            raise RuntimeError('native own matrix does not follow observed filter body')
        return True

    def binding_pending(self, value):
        # Original update198 clears target and schedules a deferred callback.
        # This short observed state is not counted as ready, never grants PNG
        # or completion, and cannot erase an already established ready clock.
        return bool(value.get('present') and value['owner_id'] == self.avatar_owner
            and value['vehicle_owner_id'] == self.vehicle_owner
            and value['attached_vehicle_id'] == vehicle.VEHICLE_ID
            and value['attached_owner_id'] == self.vehicle_owner
            and value['attached_is_own_vehicle'] is True
            and value['filter_is_original_wg_vehicle'] is True
            and value['target_present'] is False and value['target_owner_id'] is None
            and value['target_python_identity_equal'] is False and value['target_position'] is None
            and self.latest_update is not None and self.latest_bound is None and not self.binding_open)

    def advance(self):
        if self.complete:
            return True
        if not self.active:
            raise RuntimeError('failed map binding cannot continue')
        self.advances += 1
        if self.advances > MAX_ADVANCES:
            raise RuntimeError('map binding observation budget exhausted')
        now = probe._number(self.clock(), 0, 1e10, 'diagnostic clock')
        if self.last_time is not None and now < self.last_time:
            raise RuntimeError('diagnostic clock moved backwards')
        self.last_time = now
        self.drain()
        value, current = self.native.observe(), self.native.vehicle()
        world_ready = self.world_ready(value, current)
        # These read-only exports depend on the real started original Vehicle,
        # not on matrix-wrapper identity or a later driving acceptance gate.
        # Keeping them here preserves useful evidence even if binding fails.
        if world_ready and (self.physics_data is None or self.ground_data is None):
            _emit(self.record, 'map_drive_export_context', advance=self.advances, observed_at=now,
                observation=value, vehicle=current, world_ready=True,
                binding_acceptance_required=False, movement_requested=False)
        if world_ready and self.physics_data is None:
            data = self.native.physics()
            if (data['vehicle_id'] != vehicle.VEHICLE_ID
                    or data['vehicle_owner_id'] != self.vehicle_owner
                    or data['type_compact_descr'] != 3329
                    or data['compact_descr_sha256'] != self.expected['compact_descr_sha256']):
                raise RuntimeError('physics export belongs to a different native descriptor')
            self.physics_data = data
            _emit(self.record, 'map_drive_physics', advance=self.advances, observed_at=now, **data)
        if world_ready and self.ground_data is None:
            self.ground_data = self.native.ground_samples()
            _emit(self.record, 'map_drive_ground', advance=self.advances, observed_at=now, **self.ground_data)
        motion, binding = self.native.motion(), self.native.binding()
        self.drain_movement()
        self.drain_binding()
        bound = self.binding_ready(binding, motion) if world_ready and motion.get('present') else False
        pending_callback = world_ready and not bound and self.binding_pending(binding)
        _emit(self.record, 'map_drive_state', advance=self.advances, observed_at=now, phase=self.phase,
            observation=value, vehicle=current, motion=motion, binding=binding,
            world_ready=world_ready, binding_ready=bound, original_binding_callback_pending=bool(pending_callback),
            latest_update_call_id=None if self.latest_update is None else self.latest_update['returned']['call_id'],
            latest_binding_call_id=None if self.latest_bound is None else self.latest_bound['returned']['call_id'])
        if self.forward_attempted and not self.stop_attempted and now-self.started_at >= MAX_COMMAND_SECONDS:
            raise RuntimeError('original stop not reached within movement budget')
        if not world_ready or not bound:
            if pending_callback and self.last_ready is not None:
                if now-self.last_ready > MAX_GAP:
                    raise RuntimeError('original deferred binding did not finish within observation gap')
                if (motion['period'] != 3 or motion['period_end_time'] != 160.0 or motion['period_length'] != 60.0
                        or motion['is_on_arena'] is not True or motion['cruise_mode'] != 0
                        or current['roster']['avatar_ready'] is not True):
                    raise RuntimeError('native phase changed while awaiting original deferred callback')
                pending_positions = [_position(motion[key]) for key in ('entity_position', 'entity_matrix_position',
                                     'model_matrix_position', 'own_matrix_position')]
                pending_positions.append(_position(binding['body_matrix_position']))
                if any(abs(p[0]-ORIGIN[0]) > XZ_TOLERANCE or p[2] < ORIGIN[2]-XZ_TOLERANCE
                       or p[2] > TARGET[2]+XZ_TOLERANCE for p in pending_positions):
                    raise RuntimeError('native pose escaped while awaiting original deferred callback')
                if self.phase in ('hold', 'after_png') and not all(_near(p, TARGET) for p in pending_positions):
                    raise RuntimeError('native held pose changed during deferred binding')
                if self.phase == 'waiting_binding':
                    self.ready_since = None
                    self.ready_samples = 0
                return False
            if self.pending_png is not None or self.forward_attempted:
                raise RuntimeError('native world or provider binding lost during checkpoint')
            self.ready_since = self.last_ready = None
            self.ready_samples = 0
            return False
        if self.last_ready is not None and now - self.last_ready > MAX_GAP:
            raise RuntimeError('map binding observation gap exceeded')
        if motion['period'] != 3:
            if self.pending_png is not None or self.forward_attempted or motion['period'] > 3:
                raise RuntimeError('test-lab BATTLE phase lost')
            self.ready_since = self.last_ready = None
            self.ready_samples = 0
            return False
        if (motion['owner_id'] != self.avatar_owner or motion['vehicle_owner_id'] != self.vehicle_owner
                or motion['period_end_time'] != 160.0 or motion['period_length'] != 60.0
                or motion['additional_info_is_none'] is not True or motion['is_on_arena'] is not True
                or motion['cruise_mode'] != 0 or current['roster']['avatar_ready'] is not True):
            raise RuntimeError('actual binding period/owner differs from test policy')
        server_time = probe._number(motion['server_time'], 99.0, 158.0, 'native server time')
        if self.last_server_time is not None and server_time < self.last_server_time:
            raise RuntimeError('native server clock moved backwards')
        self.last_server_time = server_time
        if self.ready_since is None:
            self.ready_since = now
        self.last_ready, self.ready_samples = now, self.ready_samples + 1
        positions = [_position(motion[key]) for key in ('entity_position', 'entity_matrix_position',
                     'model_matrix_position', 'own_matrix_position')]
        positions.append(_position(binding['body_matrix_position']))
        pos = positions[0]
        if any(abs(p[0]-ORIGIN[0]) > XZ_TOLERANCE or p[2] < ORIGIN[2]-XZ_TOLERANCE
               or p[2] > TARGET[2]+XZ_TOLERANCE for p in positions):
            raise RuntimeError('native entity/provider escaped bounded server path')
        if not self.forward_attempted and not all(_near(p, ORIGIN) for p in positions):
            raise RuntimeError('native matrix changed before authorized movement')
        if self.forward_attempted and not self.stop_attempted and now-self.started_at >= MAX_COMMAND_SECONDS:
            raise RuntimeError('original stop not reached within movement budget')
        at_target = all(_near(p, TARGET) for p in positions)
        if self.phase in ('hold', 'after_png') and not at_target:
            raise RuntimeError('native matrices changed after original stop')
        if self.phase == 'waiting_binding':
            if self.ready_samples >= 3 and now-self.ready_since >= MIN_BASELINE_SECONDS:
                self.baseline_binding = dict(own=list(binding['own_matrix_position']), body=list(binding['body_matrix_position']))
                self.phase = 'before_png'
                self._request(SCREENSHOTS[0], now)
            return False
        if self.pending_png is not None:
            screenshot = self.native.screenshot(self.pending_png)
            if screenshot is None:
                if self.advances-self.png_advance >= MAX_PNG_ADVANCES:
                    raise RuntimeError('actual map binding PNG budget exhausted')
                return False
            if (type(screenshot) is not dict or screenshot.get('basename') != self.pending_png
                    or screenshot.get('png_container_valid') is not True):
                raise ValueError('actual owned map binding PNG required')
            self.screenshots.append(screenshot)
            _emit(self.record, 'map_drive_screenshot', advance=self.advances, observed_at=now, **screenshot)
            self.pending_png = None
            if len(self.screenshots) == 1:
                self.command('forward', now)
                self.phase = 'wait_target'
                return False
            own_delta = [binding['own_matrix_position'][i]-self.baseline_binding['own'][i] for i in range(3)]
            body_delta = [binding['body_matrix_position'][i]-self.baseline_binding['body'][i] for i in range(3)]
            if any(abs(delta[2]-2.0) > 2*XZ_TOLERANCE for delta in (own_delta, body_delta)):
                raise RuntimeError('native provider did not follow the complete measured displacement')
            self.complete, self.active, self.phase = True, False, 'complete'
            _emit(self.record, 'map_drive_complete', advance=self.advances, observed_at=now,
                avatar_owner_id=self.avatar_owner, vehicle_owner_id=self.vehicle_owner,
                update_call_id=self.latest_update['returned']['call_id'],
                binding_call_id=self.latest_bound['returned']['call_id'],
                forward_call_id=self.forward_pair['returned']['call_id'], stop_call_id=self.stop_pair['returned']['call_id'],
                forward_at=self.started_at, stopped_at=self.stopped_at, hold_began_at=self.hold_since,
                hold_seconds=now-self.hold_since, own_matrix_delta=own_delta, body_matrix_delta=body_delta,
                screenshots=2, lab_target=list(TARGET), native_attachment_observed=True,
                matrix_target_assigned=False, entity_position_assigned=False,
                vertical_provider_physics_acceptance='NOT_RUN',
                full_drive_acceptance='NOT_RUN', surface_acceptance='NOT_RUN', server_authority_acceptance='NOT_RUN',
                native_pixel_acceptance='NOT_RUN', clean_teardown_acceptance='NOT_RUN', compatibility_acceptance=False)
            return True
        if self.phase == 'wait_target' and at_target:
            self.command('stop', now)
            self.phase, self.hold_since = 'hold', now
            return False
        if self.phase == 'hold' and now-self.hold_since >= MIN_HOLD_SECONDS:
            self.phase = 'after_png'
            self._request(SCREENSHOTS[1], now)
        return False

    def _request(self, basename, now):
        self.native.request(basename)
        self.pending_png, self.png_advance = basename, self.advances
        _emit(self.record, 'map_drive_screenshot_requested', advance=self.advances, observed_at=now,
              basename=basename, writer='BigWorld.screenShot', pixel_acceptance='NOT_RUN')


def arm(record, settings):
    global _run, _native, _arm_attempted
    if _arm_attempted or _closing:
        raise RuntimeError('map binding scenario already armed or closing')
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
    return False if _run is None or _closing else _run.note_geometry(space_id, path)


def note_movement_call(phase, method, line, offset, call_id, owner_id, data):
    return False if _run is None or _closing else _run.note_movement(phase, method, line, offset, call_id, owner_id, data)


def note_map_drive_call(phase, method, line, offset, call_id, owner_id, data):
    return False if _run is None or _closing else _run.note_binding(phase, method, line, offset, call_id, owner_id, data)


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
        _emit(record, 'map_drive_error', advance=_run.advances, error_type=type(error).__name__,
            stop_error_type=stop_error, forward_attempted=_run.forward_attempted,
            stop_attempted=_run.stop_attempted, completion=False, compatibility_acceptance=False)
        raise


def fini(record, native_cleanup):
    global _closing, _finished_cleanup
    if _finished_cleanup:
        if _cleanup_errors:
            raise RuntimeError('map binding cleanup previously failed: ' + ', '.join(_cleanup_errors))
        return
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
            _emit(record, 'map_drive_cleanup', stage=name, outcome='FAIL' if failed else 'PASS', error_type=failed)
        except Exception as error:
            _cleanup_errors.append(name + ':record:' + type(error).__name__)
    _finished_cleanup = True
    if _cleanup_errors:
        raise RuntimeError('map binding cleanup failed: ' + ', '.join(_cleanup_errors))
