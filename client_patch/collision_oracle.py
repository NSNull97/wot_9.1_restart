# -*- coding: utf-8 -*-
"""Bounded read-only #717 native geometry/matrix observations.

Never sets an entity, model, filter or gun-rotator property. Pure local Math
objects and original hit testers are queried for comparison, not fed to the
server as authority. All output belongs to the existing local trace.
"""
import math


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
    vehicles = [value for value in entities if type(value) is Vehicle.Vehicle and value.isStarted]
    if len(vehicles) != 2:
        raise ValueError('two started vehicles required for collision oracle')
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
                   component=('Chassis', 'Hull', 'Turret_01', 'Gun_02')[index],
                   materials=material_facts(description), source='original component MaterialInfo',
                   observer_mutated_gameplay=False)
        record('shared_collision_component_oracle', schema=1, entity_id=entity.id,
               model=matrix_facts(model, Math), position=vector(entity.position),
               turret_yaw=float(Math.Matrix(entity.appearance.turretMatrix).yaw),
               gun_pitch=float(Math.Matrix(entity.appearance.gunMatrix).pitch),
               components=rows, observer_mutated_gameplay=False)
    # Local hit geometry is shared by both stock MS-1s; sample it once. Test
    # six directions and several plate heights, without firing or aiming.
    components = vehicles[0].getComponents()
    for index, name in ((1, 'Hull'), (2, 'Turret_01'), (3, 'Gun_02')):
        tester = components[index][0]['hitTester']
        if not tester.isBspModelLoaded():
            raise ValueError('native collision model has not loaded')
        bounds = [vector(tester.bbox[i]) for i in range(2)]
        if not isinstance(tester.bspModelName, basestring) or len(tester.bspModelName) > 256:
            raise ValueError('native collision model name bound')
        rays = []
        for axis in range(3):
            for offset in (-0.25, 0.05, 0.25, 0.5):
                start = [0.1, offset, 0.15]
                end = list(start)
                start[axis], end[axis] = -4., 4.
                for reverse in (False, True):
                    a, b = (end, start) if reverse else (start, end)
                    hits = tester.localHitTest(Math.Vector3(*a), Math.Vector3(*b))
                    values = []
                    if hits is not None:
                        for hit in hits:
                            if len(hit) != 4 or len(values) >= 128:
                                raise ValueError('native localHitTest result bound')
                            distance, unused, angle_cos, material = hit
                            if (not 0. <= distance <= 8.001 or not -1.001 <= angle_cos <= 1.001
                                    or type(material) not in (int, long) or not 0 <= material <= 65535):
                                raise ValueError('native localHitTest facts invalid')
                            values.append(dict(distance=float(distance), angle_cos=float(angle_cos), material=material))
                    rays.append(dict(start=a, end=b, hits=values))
        record('shared_collision_local_oracle', schema=1, component=name, rays=rays,
               native_bounds=bounds, bsp_model=tester.bspModelName,
               source='original hitTester.localHitTest', observer_mutated_gameplay=False)
