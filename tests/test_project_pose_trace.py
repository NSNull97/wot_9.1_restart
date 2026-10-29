# -*- coding: utf-8 -*-
"""NET-01 10 Hz pose trace; mocks do not prove the native client reads it."""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'client_patch'))
import project_pose_trace as m


class Vec(object):
    def __init__(self, x, y, z):
        self.x, self.y, self.z = x, y, z


class Avatar(object):
    playerVehicleID = 152043523
    arenaUniqueID = 77


class Vehicle(object):
    def __init__(self, entity_id, x, y=10., z=5.):
        self.id, self.position = entity_id, Vec(x, y, z)


class Other(object):
    id, position = 9, Vec(0, 0, 0)


class Engine(object):
    def __init__(self, player, entities):
        self._player, self.entities = player, dict((e.id, e) for e in entities)

    def player(self):
        return self._player

    def time(self):
        return 12.5

    def serverTime(self):
        return 140.25


class PoseTraceTests(unittest.TestCase):
    def test_settings_are_explicit_and_need_profile13(self):
        self.assertFalse(m.validate_settings({}))
        self.assertTrue(m.validate_settings({'trace_pose_10hz': True, 'enable_profile13_battle': True}))
        for bad in ({'trace_pose_10hz': None}, {'trace_pose_10hz': 1, 'enable_profile13_battle': True},
                    {'trace_pose_10hz': True}):
            self.assertRaises(ValueError, m.validate_settings, bad)

    def test_sample_reads_every_vehicle_and_times_only_for_the_avatar(self):
        engine = Engine(Avatar(), [Vehicle(152109059, 1.23456), Vehicle(152043523, -7.0), Other()])
        row = m.sample(engine, Avatar, Vehicle)
        self.assertEqual(row['vehicles'], [[152043523, -7.0, 10.0, 5.0, True], [152109059, 1.235, 10.0, 5.0, False]])
        self.assertEqual((row['native_time'], row['server_time'], row['arena_unique_id']), (12.5, 140.25, 77))
        self.assertFalse(row['observer_mutated_gameplay'])
        self.assertIsNone(m.sample(Engine(object(), []), Avatar, Vehicle))

    def test_unbounded_values_and_counts_fail_closed(self):
        self.assertRaises(ValueError, m.sample, Engine(Avatar(), [Vehicle(1, float('nan'))]), Avatar, Vehicle)
        self.assertRaises(ValueError, m.sample, Engine(Avatar(), [Vehicle(1, 5000.)]), Avatar, Vehicle)
        many = [Vehicle(n, 0.) for n in range(m.MAX_VEHICLES + 1)]
        self.assertRaises(ValueError, m.sample, Engine(Avatar(), many), Avatar, Vehicle)


if __name__ == '__main__':
    unittest.main()
