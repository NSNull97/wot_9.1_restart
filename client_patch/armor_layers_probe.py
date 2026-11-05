# -*- coding: utf-8 -*-
"""SHELL-01 steps 4-5: bounded read-only native armour observation in a ready Hangar.

For a closed list of #717 vehicles this builds the original stock descriptor
(items.vehicles.VehicleDescr), loads each component's original collision model
through ModelHitTester (BigWorld.WGBspCollisionModel) and records the native
collideSegment answer (ModelHitTester.localHitTest) for a fixed grid of
component-local segments, plus the native MaterialInfo table of every component
and the loaded shell calibres of the FV215b (183) gun.

Never selects, buys or changes a vehicle, never sends an RPC, never writes
account/fixture data. A collision model the probe loads itself is released
again; one already loaded by the client is left as it was. Output: trace records
only (each below the 64 KiB record bound).
"""
import math

VEHICLES = ('ussr:KV-3', 'china:Ch22_113', 'france:Bat_Chatillon25t', 'ussr:T62A', 'uk:GB48_FV215b_183')
CALIBER_VEHICLE = 'uk:GB48_FV215b_183'
COMPONENTS = ('chassis', 'hull', 'turret', 'gun')
FRACTIONS = (0.1, 0.3, 0.5, 0.7, 0.9)
MARGIN = 0.5
MAX_HITS = 64
MATERIAL_FLAGS = ('useArmorHomogenization', 'useHitAngle', 'useAntifragmentationLining',
                  'mayRicochet', 'collideOnceOnly', 'continueTraceIfNoHit')
MATERIAL_SCALARS = ('armor', 'vehicleDamageFactor', 'chanceToHitByProjectile', 'chanceToHitByExplosion')
_done = False


def _number(value, low, high, label):
    if type(value) not in (int, long, float) or math.isnan(value) or math.isinf(value) or not low <= value <= high:
        raise ValueError('armor layers probe bound: ' + label)
    return float(value)


def _vector(value):
    return [_number(value[i], -100000., 100000., 'vector') for i in range(3)]


def _materials(description):
    materials = description.get('materials') or {}
    if not isinstance(materials, dict) or len(materials) > 64:
        raise ValueError('native material table bound')
    rows = []
    for kind in sorted(materials):
        material = materials[kind]
        if type(kind) not in (int, long) or not 0 <= kind <= 65535 or material.kind != kind:
            raise ValueError('native material kind differs')
        row = dict(kind=kind, extra=None if material.extra is None else str(material.extra)[:64],
                   damageKind=int(material.damageKind))
        for name in MATERIAL_FLAGS:
            value = getattr(material, name)
            if type(value) is not bool:
                raise ValueError('native material boolean differs')
            row[name] = value
        for name in MATERIAL_SCALARS:
            value = getattr(material, name)
            row[name] = None if value is None else _number(value, 0., 100000., name)
        rows.append(row)
    return rows


def _segments(bounds):
    low, high = bounds
    for axis in range(3):
        others = [i for i in range(3) if i != axis]
        for u in FRACTIONS:
            for v in FRACTIONS:
                point = [0., 0., 0.]
                point[others[0]] = low[others[0]] + (high[others[0]] - low[others[0]]) * u
                point[others[1]] = low[others[1]] + (high[others[1]] - low[others[1]]) * v
                start, end = list(point), list(point)
                start[axis], end[axis] = low[axis] - MARGIN, high[axis] + MARGIN
                yield axis, start, end
                yield axis, end, start


def _hits(tester, Math, start, end):
    found = tester.localHitTest(Math.Vector3(*start), Math.Vector3(*end))
    length = math.sqrt(sum((end[i] - start[i]) ** 2 for i in range(3)))
    rows = []
    for hit in found or ():
        if len(hit) != 4 or len(rows) >= MAX_HITS:
            raise ValueError('native localHitTest result bound')
        distance, _, angle_cos, material = hit
        if type(material) not in (int, long) or not 0 <= material <= 65535:
            raise ValueError('native localHitTest material bound')
        rows.append([round(_number(distance, 0., length + 0.001, 'distance'), 6),
                     round(_number(angle_cos, -1.001, 1.001, 'angle'), 6), material])
    return rows


def _component(record, Math, type_name, name, description):
    tester = description.get('hitTester')
    if tester is None:
        record('armor_layers_component', vehicle=type_name, component=name, status='NO_HIT_TESTER')
        return
    loaded_before = tester.isBspModelLoaded()
    if not loaded_before:
        tester.loadBspModel()
    try:
        bounds = [_vector(tester.bbox[i]) for i in range(2)]
        model = tester.bspModelName
        if not isinstance(model, basestring) or len(model) > 256:
            raise ValueError('native collision model name bound')
        record('armor_layers_component', vehicle=type_name, component=name, status='LOADED',
               bsp_model=model, native_bounds=bounds, loaded_before=loaded_before,
               materials=_materials(description), observer_mutated_gameplay=False)
        by_axis = {}
        for axis, start, end in _segments(bounds):
            by_axis.setdefault(axis, []).append(dict(start=[round(x, 6) for x in start], end=[round(x, 6) for x in end],
                                                     hits=_hits(tester, Math, start, end)))
        for axis in sorted(by_axis):
            record('armor_layers_rays', vehicle=type_name, component=name, axis=axis, rays=by_axis[axis],
                   source='original ModelHitTester.localHitTest (BigWorld collideSegment)',
                   observer_mutated_gameplay=False)
    finally:
        if not loaded_before:
            tester.releaseBspModel()


def _calibers(record, vehicles, type_name):
    desc = vehicles.VehicleDescr(typeName=type_name)
    rows = []
    for shot in desc.gun['shots']:
        shell = shot['shell']
        caliber = shell['caliber']
        rows.append(dict(shell_id=list(shell['id']), kind=str(shell['kind']), caliber_repr=repr(caliber),
                         caliber_type=type(caliber).__name__, piercing_power=[float(shot['piercingPower'][0]),
                                                                              float(shot['piercingPower'][1])]))
    record('armor_layers_calibers', vehicle=type_name, gun=desc.gun['name'], shells=rows,
           source='original items.vehicles descriptor (loaded shells)', observer_mutated_gameplay=False)


def export(record):
    """One-shot read after a genuine ready Hangar; the caller arms it from test control."""
    global _done
    if _done:
        raise ValueError('armor layers probe already ran')
    _done = True
    import Math
    from items import vehicles
    for type_name in VEHICLES:
        native_id = vehicles.g_list.getIDsByName(type_name)
        desc = vehicles.VehicleDescr(typeName=type_name)
        if tuple(desc.type.id) != tuple(native_id) or desc.type.name != type_name:
            raise ValueError('original vehicle lookup/descriptor identity mismatch')
        record('armor_layers_vehicle', vehicle=type_name, compact_descr=desc.makeCompactDescr().encode('hex'),
               hull_position=_vector(desc.chassis['hullPosition']), turret_position=_vector(desc.hull['turretPositions'][0]),
               gun_position=_vector(desc.turret['gunPosition']))
        for name in COMPONENTS:
            _component(record, Math, type_name, name, getattr(desc, name))
    _calibers(record, vehicles, CALIBER_VEHICLE)
