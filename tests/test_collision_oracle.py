"""Synthetic native-API boundaries; no claim of actual BigWorld execution."""
import copy
import hashlib
import math
import sys
from types import SimpleNamespace as NS
import unittest
from unittest import mock

from client_patch import collision_oracle as oracle
from tools import client_marker_oracle as audit

# Only the test host needs aliases; shipped collector remains original Python2.7.
oracle.long = int
oracle.basestring = str


class Vec(tuple):
    def __new__(cls, *values):
        return tuple.__new__(cls, values)

    def __add__(self, other):
        return Vec(*(a + b for a, b in zip(self, other)))

    def __sub__(self, other):
        return Vec(*(a - b for a, b in zip(self, other)))

    @property
    def length(self):
        return math.sqrt(sum(x*x for x in self))


class Matrix:
    yaw = pitch = 0.

    def __init__(self, ignored=None):
        pass

    def setRotateYPR(self, angles):
        pass

    def applyPoint(self, value):
        return value

    def applyToAxis(self, index):
        return [float(i == index) for i in range(3)]


MATH = NS(Vector3=Vec, Matrix=Matrix)


def player(kind="is7"):
    identity = audit.VEHICLE_PROFILES[kind]
    profile = audit.shot_profile(kind)
    shell = dict(compactDescr=profile['shell_compact_descriptor'], kind='ARMOR_PIERCING',
                 caliber=profile['caliber'], damageRandomization=.25,
                 piercingPowerRandomization=.25)
    descriptor = NS(type=NS(name=identity['vehicle_name'], compactDescr=identity['vehicle_compact_descriptor']),
                    gun={'compactDescr': identity['gun_compact_descriptor']},
                    shot=dict(shell=shell, piercingPower=list(profile['piercing_power']), maxDistance=720.))
    return NS(vehicleTypeDescriptor=descriptor, getOwnVehiclePosition=lambda: Vec(0., 0., 0.))


class HitTester:
    def __init__(self, name, prefix):
        self.bspModelName = prefix + name + '.model'
        self.bbox = [[-.3, -.2, -.9], [.4, .48, 5.99207878112793]]
        self.calls = []
        self.hit_distance = 1.

    def isBspModelLoaded(self):
        return True

    def localHitTest(self, start, end):
        self.calls.append((start, end))
        return [(self.hit_distance, None, .5, 1)]


class Vehicle:
    def __init__(self, actor_id, kind="is7"):
        self.id, self.isStarted = actor_id, True
        self.typeDescriptor = player(kind).vehicleTypeDescriptor
        self.model = NS(matrix=Matrix())
        self.appearance = NS(turretMatrix=Matrix(), gunMatrix=Matrix())
        self.position = Vec(0., 0., 0.)
        names, _, prefix = oracle._layout(oracle._vehicle_profile(self.typeDescriptor))
        mat = NS(kind=1, extra=None, armor=240., vehicleDamageFactor=1.,
                 chanceToHitByProjectile=1., chanceToHitByExplosion=1., damageKind=0)
        for name in ('useArmorHomogenization', 'useHitAngle', 'useAntifragmentationLining',
                     'mayRicochet', 'collideOnceOnly', 'continueTraceIfNoHit'):
            setattr(mat, name, False)
        self.components = [({'hitTester': HitTester(name, prefix), 'materials': {1: mat}}, Matrix(), True)
                           for name in names]

    def getComponents(self):
        return self.components


class CollisionOracleTests(unittest.TestCase):
    def test_exact_mounted_ap_profiles_and_legacy_shape(self):
        self.assertEqual(oracle._marker_shot_facts(player('ms1')), audit.PROFILE)
        self.assertEqual(oracle._marker_shot_facts(player()), audit.IS7_PROFILE)

    def test_native_vector_pair_uses_only_two_fixed_numeric_indices(self):
        class NativeVectorPair:
            def __init__(self, values):
                self.values, self.reads = values, []

            def __len__(self):
                raise AssertionError('native vector length API is not required')

            def __iter__(self):
                raise AssertionError('native vector must not be iterated')

            def __getitem__(self, index):
                self.reads.append(index)
                if type(index) is not int or index not in (0, 1):
                    raise AssertionError('only source indices0/1 are permitted')
                return self.values[index]

        for kind in ('ms1', 'is7'):
            p = player(kind)
            value = NativeVectorPair(audit.shot_profile(kind)['piercing_power'])
            p.vehicleTypeDescriptor.shot['piercingPower'] = value
            self.assertEqual(oracle._marker_shot_facts(p), audit.shot_profile(kind))
            self.assertEqual(value.reads, [0, 1])
        for bad in (True, '250', float('nan'), float('inf'), -1., 10**500, 249.):
            p = player()
            value = NativeVectorPair([bad, 240.])
            p.vehicleTypeDescriptor.shot['piercingPower'] = value
            with self.subTest(value=bad), self.assertRaises(ValueError):
                oracle._marker_shot_facts(p)
            self.assertTrue(all(index in (0, 1) for index in value.reads))

    def test_unknown_vehicle_gun_swaps_and_cross_profile_shell_rejected(self):
        for attr, value in (('name', 'ussr:Other'), ('compactDescr', 3329), ('compactDescr', True)):
            p = player()
            setattr(p.vehicleTypeDescriptor.type, attr, value)
            with self.subTest(attr=attr, value=value), self.assertRaises(ValueError):
                oracle._marker_shot_facts(p)
        p = player()
        p.vehicleTypeDescriptor.gun['compactDescr'] = 5892
        with self.assertRaises(ValueError):
            oracle._marker_shot_facts(p)
        for value in (2570, 14858, 15114, True):
            p = player()
            p.vehicleTypeDescriptor.shot['shell']['compactDescr'] = value
            with self.subTest(shell=value), self.assertRaises(ValueError):
                oracle._marker_shot_facts(p)

    def test_malformed_or_nonfinite_shot_facts_rejected(self):
        for value in (True, '250', float('nan'), float('inf'), -1, 10**500):
            p = player()
            p.vehicleTypeDescriptor.shot['piercingPower'][0] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                oracle._marker_shot_facts(p)
        p = player()
        p.vehicleTypeDescriptor.shot['piercingPower'].append(10)
        with self.assertRaisesRegex(ValueError, 'pair shape'):
            oracle._marker_shot_facts(p)

    def collect(self, p, vehicles):
        rows = []
        modules = {'Math': MATH, 'Vehicle': NS(Vehicle=Vehicle),
                   'projectile_trajectory': NS(getShotAngles=lambda *args: (0., 0.))}
        with mock.patch.dict(sys.modules, modules), mock.patch.object(oracle, 'collect_ap_marker') as marker:
            oracle.collect(p, vehicles, lambda event, **kw: rows.append(dict(event=event, **kw)))
            marker.assert_called_once()
        return rows

    def test_is7_labels_bsp_pins_native_bbox_and_full_length_rays(self):
        vehicles = [Vehicle(1), Vehicle(2)]
        rows = self.collect(player(), vehicles)
        local = [r for r in rows if r['event'] == 'shared_collision_local_oracle']
        self.assertEqual([r['component'] for r in local], ['Hull', 'Turret_01', 'Gun_01'])
        self.assertEqual(local[2]['native_bounds'][1][2], 5.99207878112793)
        self.assertEqual(len(local[2]['rays']), 24)
        self.assertEqual(local[2]['rays'][16]['start'][2], -8.)
        self.assertEqual(local[2]['rays'][16]['end'][2], 8.)
        self.assertTrue(all(r['vehicle_profile'] == audit.VEHICLE_PROFILES['is7'] for r in local))
        materials = [r['component'] for r in rows if r['event'] == 'shared_collision_material_oracle']
        self.assertEqual(materials, ['Chassis', 'Hull', 'Turret_01', 'Gun_01'] * 2)

    def test_ms1_labels_and_ray_plan_unchanged(self):
        rows = self.collect(player('ms1'), [Vehicle(1, 'ms1'), Vehicle(2, 'ms1')])
        local = [r for r in rows if r['event'] == 'shared_collision_local_oracle']
        self.assertEqual(local[-1]['component'], 'Gun_02')
        self.assertEqual(local[-1]['rays'][16]['start'][2], -4.)
        self.assertEqual(local[-1]['rays'][16]['end'][2], 4.)

    def test_mixed_actor_profile_wrong_bsp_and_long_hit_rejected(self):
        with self.assertRaisesRegex(ValueError, 'matching'):
            self.collect(player(), [Vehicle(1), Vehicle(2, 'ms1')])
        vehicles = [Vehicle(1), Vehicle(2)]
        vehicles[0].components[3][0]['hitTester'].bspModelName = 'vehicles/other/Gun_01.model'
        with self.assertRaisesRegex(ValueError, 'model differs'):
            self.collect(player(), vehicles)
        vehicles = [Vehicle(1), Vehicle(2)]
        vehicles[0].components[1][0]['hitTester'].hit_distance = 16.002
        with self.assertRaisesRegex(ValueError, 'facts invalid'):
            self.collect(player(), vehicles)

    def marker(self, p, mutate=None, code_sha=audit.METHOD_SHA):
        rows = []
        def original(receiver, point, armor):
            receiver.call('Crosshair.setMarkerType', [audit.expected_label(point.length, armor, 'is7')])
            if mutate:
                mutate()
        original.func_code = NS(co_firstlineno=2772, co_argcount=3,
                                co_filename=audit.METHOD_FILE, co_code=b'synthetic-test-code')
        modules = {'BigWorld': NS(player=lambda: p),
                   'AvatarInputHandler.control_modes': NS(_FlashGunMarker=NS(_changeColor=NS(im_func=original)))}
        try:
            with mock.patch.dict(sys.modules, modules), mock.patch.object(hashlib, 'sha256',
                    return_value=NS(hexdigest=lambda: code_sha)):
                oracle.collect_ap_marker(p, lambda event, **kw: rows.append(dict(event=event, **kw)), MATH)
        except ValueError:
            return rows
        return rows

    def test_synthetic_marker_calls_are_schema2_and_validate_without_mutation(self):
        p = player()
        before = copy.deepcopy(p.vehicleTypeDescriptor.shot)
        rows = self.marker(p)
        self.assertEqual(rows[0]['status'], 'PASS_NATIVE_CALLS')
        self.assertEqual(len(audit.validate_event(rows[0], 'a', 'is7')), 60)
        self.assertEqual(p.vehicleTypeDescriptor.shot, before)

    def test_marker_method_pin_and_midcall_profile_drift_emit_failure(self):
        p = player()
        rows = self.marker(p, code_sha='0'*64)
        self.assertEqual(rows[0]['status'], 'FAIL')
        self.assertEqual(rows[0]['completed_cases'], 0)
        rows = self.marker(p, lambda: p.vehicleTypeDescriptor.gun.__setitem__('compactDescr', 5892))
        self.assertEqual(rows[0]['schema'], 2)
        self.assertEqual(rows[0]['status'], 'FAIL')
        self.assertEqual(rows[0]['completed_cases'], 0)


if __name__ == '__main__':
    unittest.main()
