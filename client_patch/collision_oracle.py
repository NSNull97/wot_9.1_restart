# -*- coding: utf-8 -*-
"""Bounded read-only #717 native geometry/matrix observations.

Never sets an entity, model, filter or gun-rotator property. Pure local Math
objects and original hit testers are queried for comparison, not fed to the
server as authority. All output belongs to the existing local trace.
"""
import math


def _vehicle_profile(descriptor):
    """Closed #717 mounted profiles; never infer a vehicle from its shell alone."""
    name = descriptor.type.name
    vehicle = descriptor.type.compactDescr
    gun = descriptor.gun['compactDescr']
    if (type(vehicle) not in (int, long) or type(gun) not in (int, long) or
            (name, vehicle, gun) not in (('ussr:MS-1', 3329, 5892),
                                        ('ussr:IS-7', 7169, 14852))):
        raise ValueError('collision oracle requires a pinned #717 mounted vehicle profile')
    return dict(vehicle_name=name, vehicle_compact_descriptor=vehicle,
                gun_compact_descriptor=gun)


def _layout(profile):
    if profile['vehicle_name'] == 'ussr:IS-7':
        return ('Chassis', 'Hull', 'Turret_01', 'Gun_01'), 8., 'vehicles/russian/R45_IS-7/collision/'
    return ('Chassis', 'Hull', 'Turret_01', 'Gun_02'), 4., 'vehicles/russian/R11_MS-1/collision/'


def _shot_number(value):
    if (type(value) not in (int, long, float) or
            not 0. <= value <= 100000. or math.isnan(value) or math.isinf(value)):
        raise ValueError('original marker shot scalar bound')
    return float(value)


class _MarkerCallCapture(object):
    """A local receiver for one original marker call; no Flash component."""
    def __init__(self):
        self._curColors = dict((name, name) for name in
                               ('great_pierced', 'little_pierced', 'not_pierced'))
        self.calls = []

    def call(self, name, args):
        if (self.calls or name != 'Crosshair.setMarkerType' or
                type(args) is not list or len(args) != 1 or args[0] not in self._curColors):
            raise ValueError('original marker callback shape differs')
        self.calls.append(dict(name=name, args=list(args)))


def _marker_shot_facts(player):
    profile = _vehicle_profile(player.vehicleTypeDescriptor)
    shot = player.vehicleTypeDescriptor.shot
    shell = shot['shell']
    if type(shot['piercingPower']) not in (list, tuple) or len(shot['piercingPower']) != 2:
        raise ValueError('original marker piercing pair shape')
    values = [_shot_number(value) for value in shot['piercingPower']]
    values.extend(_shot_number(value) for value in
                  (shot['maxDistance'], shell['caliber'],
                   shell['damageRandomization'], shell['piercingPowerRandomization']))
    expected_shell, expected_values = (2570, [34., 27., 720., 37., 0.25, 0.25])
    if profile['vehicle_name'] == 'ussr:IS-7':
        expected_shell, expected_values = (14602, [250., 240., 720., 130., 0.25, 0.25])
    if (type(shell['compactDescr']) not in (int, long) or shell['compactDescr'] != expected_shell or
            shell['kind'] != 'ARMOR_PIERCING' or values != expected_values):
        raise ValueError('marker oracle requires the pinned mounted vehicle AP shot')
    return dict(shell_compact_descriptor=shell['compactDescr'], shell_kind=shell['kind'],
                piercing_power=values[:2], max_distance=values[2], caliber=values[3],
                damage_randomization=values[4], piercing_randomization=values[5])


def collect_ap_marker(player, record, Math):
    """Observe the original #717 UI predictor; never a penetration verdict.

    _changeColor reads only the real player descriptor/position plus the dummy
    receiver's _curColors/call. It does not use a component or alter its receiver.
    No constructor, update, global patch or descriptor mutation is involved.
    All calls are synchronous; reject any observed player, shot or position drift.
    """
    import BigWorld
    import hashlib
    from AvatarInputHandler.control_modes import _FlashGunMarker
    samples = []
    before_position = None
    before_shot = None
    before_profile = None
    schema = 1
    try:
        original = _FlashGunMarker._changeColor.im_func
        code = original.func_code
        method_sha = hashlib.sha256(code.co_code).hexdigest()
        if (code.co_firstlineno != 2772 or code.co_argcount != 3 or
                code.co_filename != 'scripts/client/AvatarInputHandler/control_modes.py' or
                method_sha != '928595f683fa01b6f07fd27bf209187f3132ca51c0c427f3464e59d8830d14a3'):
            raise ValueError('original marker method pin differs')
        if BigWorld.player() is not player:
            raise ValueError('original marker active player differs')
        descriptor = player.vehicleTypeDescriptor
        before_profile = _vehicle_profile(descriptor)
        schema = 2 if before_profile['vehicle_name'] == 'ussr:IS-7' else 1
        shot_object = descriptor.shot
        before_position = vector(player.getOwnVehiclePosition())
        before_shot = _marker_shot_facts(player)
        origin = Math.Vector3(*before_position)
        # 36 fixed-armor cases plus 24 transition cases = a hard cap of 60.
        cases = [(distance, armor, None) for distance in
                 (0., 100., 100.01, 300., 500., 600., 719.99, 720., 720.01)
                 for armor in (0., 8., 16., 18.)]
        cases.extend((distance, None, ratio) for distance in (100., 300., 500., 719.99)
                     for ratio in (89.9999, 90., 90.0001, 149.9999, 150., 150.0001))
        if len(cases) != 60:
            raise ValueError('marker oracle case count differs')
        for distance, armor, threshold in cases:
            point = origin + Math.Vector3(distance, 0., 0.)
            measured_distance = float((point - player.getOwnVehiclePosition()).length)
            if (math.isnan(measured_distance) or math.isinf(measured_distance) or
                    not 0. <= measured_distance <= 721.):
                raise ValueError('native marker measured distance bound')
            if threshold is not None:
                # This translation selects inputs around source branch points.
                # It is not recorded as a native numeric power result; only the
                # original method's callback below is the independent oracle.
                p100, p500 = before_shot['piercing_power']
                power_for_input = (p100 if measured_distance <= 100. else
                    max(0., p100 + (p500 - p100) * (measured_distance - 100.) / 400.))
                if not 0. < power_for_input <= 100000.:
                    raise ValueError('marker transition input power bound')
                armor = power_for_input * threshold / 100.
            receiver = _MarkerCallCapture()
            original(receiver, point, armor)
            if len(receiver.calls) != 1:
                raise ValueError('original marker did not produce one callback')
            if (BigWorld.player() is not player or player.vehicleTypeDescriptor is not descriptor or
                    _vehicle_profile(descriptor) != before_profile or
                    descriptor.shot is not shot_object or _marker_shot_facts(player) != before_shot or
                    vector(player.getOwnVehiclePosition()) != before_position):
                raise ValueError('marker oracle player position or selected shot changed')
            samples.append(dict(case_id=len(samples), requested_distance=distance,
                                measured_distance=measured_distance, hit_point=vector(point),
                                armor=armor, threshold_input_ratio=threshold,
                                callback=receiver.calls[0]))
        after_position = vector(player.getOwnVehiclePosition())
        after_shot = _marker_shot_facts(player)
        after_profile = _vehicle_profile(descriptor)
        if (after_position != before_position or after_shot != before_shot or
                after_profile != before_profile):
            raise ValueError('marker oracle final position or selected shot changed')
    except Exception as error:
        record('shared_ap_marker_oracle', schema=schema, status='FAIL',
               error=str(error)[:256], completed_cases=len(samples),
               own_position_before=before_position, selected_shot_before=before_shot,
               vehicle_profile_before=before_profile,
               samples=samples, observer_mutated_gameplay=False)
        raise
    record('shared_ap_marker_oracle', schema=schema, status='PASS_NATIVE_CALLS',
           source='original _FlashGunMarker._changeColor.im_func',
           method_filename=code.co_filename, method_firstlineno=code.co_firstlineno,
           method_code_sha256=method_sha, own_position_before=before_position,
           own_position_after=after_position, selected_shot_before=before_shot,
           selected_shot_after=after_shot, samples=samples,
           vehicle_profile_before=before_profile, vehicle_profile_after=after_profile,
           server_penetration_verdict=False, observer_mutated_gameplay=False)


def vector(value):
    row = [float(value[i]) for i in range(3)]
    if any(math.isnan(x) or math.isinf(x) or abs(x) > 100000. for x in row):
        raise ValueError('collision oracle vector bound')
    return row


def matrix_facts(matrix, Math):
    return dict(origin=vector(matrix.applyPoint(Math.Vector3(0., 0., 0.))),
                axes=[vector(matrix.applyToAxis(index)) for index in range(3)])


def material_facts(description):
    materials = description['materials']
    if not isinstance(materials, dict) or not 0 < len(materials) <= 64:
        raise ValueError('native material table bound')
    rows = []
    flags = ('useArmorHomogenization', 'useHitAngle', 'useAntifragmentationLining',
             'mayRicochet', 'collideOnceOnly', 'continueTraceIfNoHit')
    scalars = ('armor', 'vehicleDamageFactor', 'chanceToHitByProjectile', 'chanceToHitByExplosion')
    for kind in sorted(materials):
        material = materials[kind]
        if type(kind) not in (int, long) or not 0 <= kind <= 65535 or material.kind != kind:
            raise ValueError('native material kind differs')
        row = dict(kind=kind, extra_is_none=material.extra is None)
        for name in flags:
            value = getattr(material, name)
            if type(value) is not bool:
                raise ValueError('native material boolean differs')
            row[name] = value
        for name in scalars:
            value = getattr(material, name)
            if value is None and name == 'armor':
                row[name] = None
                continue
            if type(value) not in (int, long, float) or math.isnan(value) or math.isinf(value) or not 0 <= value <= 100000.:
                raise ValueError('native material scalar bound')
            row[name] = float(value)
        if type(material.damageKind) not in (int, long) or not 0 <= material.damageKind <= 255:
            raise ValueError('native material damage kind bound')
        row['damageKind'] = material.damageKind
        rows.append(row)
    return rows


def collect(player, entities, record):
    import Math
    import Vehicle
    profile = _vehicle_profile(player.vehicleTypeDescriptor)
    names, extent, model_prefix = _layout(profile)
    vehicles = [value for value in entities if type(value) is Vehicle.Vehicle and value.isStarted]
    if len(vehicles) != 2:
        raise ValueError('two started vehicles required for collision oracle')
    if any(_vehicle_profile(entity.typeDescriptor) != profile for entity in vehicles):
        raise ValueError('collision oracle requires two matching mounted vehicle profiles')
    # Independent native Euler oracle, including nonzero yaw/pitch/roll.
    samples = []
    for angles in ((0., 0., 0.), (0.5, 0., 0.), (0., 0.3, 0.),
                   (0., 0., -0.2), (0.7, -0.3, 0.2), (-2.1, 0.25, -0.15)):
        matrix = Math.Matrix()
        matrix.setRotateYPR(angles)
        samples.append(dict(ypr=list(angles), matrix=matrix_facts(matrix, Math)))
    record('shared_collision_math_oracle', schema=1, samples=samples,
           observer_mutated_gameplay=False)
    from projectile_trajectory import getShotAngles
    aim_samples = []
    for angles in ((0.7, -0.3, 0.2), (-2.1, 0.25, -0.15), (0.2, 0.6, -0.5)):
        matrix = Math.Matrix()
        matrix.setRotateYPR(angles)
        matrix.translation = Math.Vector3(37., 21., -105.)
        for relative in ((0., 0., 100.), (450., -20., 310.), (-300., 60., -400.), (1., 0., 5.)):
            point = [relative[i] + (37., 21., -105.)[i] for i in range(3)]
            result = getShotAngles(player.vehicleTypeDescriptor, matrix, (0., 0.), Math.Vector3(*point))
            aim_samples.append(dict(ypr=list(angles), position=[37., 21., -105.],
                                    point=point, angles=[float(result[0]), float(result[1])]))
    record('shared_collision_tilted_aim_oracle', schema=1, samples=aim_samples,
           observer_mutated_gameplay=False)
    for entity in vehicles:
        components = entity.getComponents()
        if len(components) != 4:
            raise ValueError('original component shape differs')
        model = Math.Matrix(entity.model.matrix)
        rows = []
        for index, (description, inverse_local, attached) in enumerate(components):
            rows.append(dict(component=index, attached=bool(attached),
                             inverse_local=matrix_facts(inverse_local, Math)))
            record('shared_collision_material_oracle', schema=1, entity_id=entity.id,
                   component=names[index], vehicle_profile=profile,
                   materials=material_facts(description), source='original component MaterialInfo',
                   observer_mutated_gameplay=False)
        record('shared_collision_component_oracle', schema=1, entity_id=entity.id,
               model=matrix_facts(model, Math), position=vector(entity.position),
               turret_yaw=float(Math.Matrix(entity.appearance.turretMatrix).yaw),
               gun_pitch=float(Math.Matrix(entity.appearance.gunMatrix).pitch),
               components=rows, vehicle_profile=profile, observer_mutated_gameplay=False)
    # Local hit geometry is shared by the verified matching profiles; sample once. Test
    # six directions and several plate heights, without firing or aiming.
    components = vehicles[0].getComponents()
    for index, name in enumerate(names[1:], 1):
        tester = components[index][0]['hitTester']
        if not tester.isBspModelLoaded():
            raise ValueError('native collision model has not loaded')
        bounds = [vector(tester.bbox[i]) for i in range(2)]
        if not isinstance(tester.bspModelName, basestring) or len(tester.bspModelName) > 256:
            raise ValueError('native collision model name bound')
        if tester.bspModelName != model_prefix + name + '.model':
            raise ValueError('native collision model differs from mounted profile')
        rays = []
        for axis in range(3):
            for offset in (-0.25, 0.05, 0.25, 0.5):
                start = [0.1, offset, 0.15]
                end = list(start)
                start[axis], end[axis] = -extent, extent
                for reverse in (False, True):
                    a, b = (end, start) if reverse else (start, end)
                    hits = tester.localHitTest(Math.Vector3(*a), Math.Vector3(*b))
                    values = []
                    if hits is not None:
                        for hit in hits:
                            if len(hit) != 4 or len(values) >= 128:
                                raise ValueError('native localHitTest result bound')
                            distance, unused, angle_cos, material = hit
                            if (not 0. <= distance <= 2. * extent + 0.001 or not -1.001 <= angle_cos <= 1.001
                                    or type(material) not in (int, long) or not 0 <= material <= 65535):
                                raise ValueError('native localHitTest facts invalid')
                            values.append(dict(distance=float(distance), angle_cos=float(angle_cos), material=material))
                    rays.append(dict(start=a, end=b, hits=values))
        record('shared_collision_local_oracle', schema=1, component=name, rays=rays,
               native_bounds=bounds, bsp_model=tester.bspModelName,
               vehicle_profile=profile,
               source='original hitTester.localHitTest', observer_mutated_gameplay=False)
    collect_ap_marker(player, record, Math)
