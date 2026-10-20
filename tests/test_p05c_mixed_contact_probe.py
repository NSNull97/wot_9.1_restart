"""Authored bounded parser/measurement vectors; these never launch Jolt/native."""
import importlib.util
import math
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('p05c_mixed_contact_probe', ROOT / 'tools/p05c_mixed_contact_probe.py')
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)


class MixedContactProbeTests(unittest.TestCase):
    def test_recorded_control_parser_requires_all_actual_sequences_and_two_actors(self):
        def line(n, second='Input { throttle: 0, steer: 0, brake: true, speed_percent: 100 }'):
            return f'P05C_SCENE_INPUT battle={p.BATTLE} seq={n} actors=2 inputs=[Input {{ throttle: 1, steer: 0, brake: false, speed_percent: 100 }}, {second}] world_tick={1000+n}\n'.encode()
        raw = b''.join(line(n) for n in range(1, 2264))
        got = p.controls_from_log(raw)
        self.assertEqual(len(got), 2263)
        self.assertEqual(got[0], [p.FORWARD, p.STOP])
        for bad in [raw[:-1], raw.replace(b'seq=2 ', b'seq=3 ', 1), raw.replace(b'throttle: 1', b'throttle: 2', 1),
                    raw.replace(b'brake: false', b'brake: true', 1), b''.join(line(n) for n in range(1, 2263))]:
            with self.assertRaises(ValueError):
                p.controls_from_log(bad)

    def test_json_and_portable_members_are_closed_before_filesystem(self):
        self.assertEqual(p.decode(b'{"a":1}'), {'a': 1})
        for raw in [b'{"a":1,"a":2}', b'{"a":NaN}']:
            with self.assertRaises(ValueError):
                p.decode(raw)
        with self.assertRaises(ValueError):
            p.decode(b' ' * 20, 19)
        self.assertEqual(p.member('bin/MapDriveWorker.exe'), Path('bin/MapDriveWorker.exe'))
        for value in ['../x', '/x', 'a//b', 'a/./b', 'a/../b', 'C:/x', 'a\\x', '//server/share/x', '']:
            with self.assertRaises(ValueError):
                p.member(value)

    def test_scene_hash_uses_existing_independent_rust_vector(self):
        self.assertEqual(p.scene_hash('b' * 64, []), '3b4d76b3e9b6266fea62459b5d9d2567819a9851fc9abdc2c59640f8e089f81f')
        with self.assertRaises(ValueError):
            p.scene_hash(p.ZERO, [1])

    def test_full_body_tilt_and_stall_are_observations_not_root_cause(self):
        def frame(speed, roll=0.):
            return {'tank_contacts': [], 'actors': [{'state': {'direction': [0., 0., roll], 'speed': speed}},
                                                   {'state': {'direction': [0., 0., 0.], 'speed': 0.}}]}
        frames = [frame(0.), frame(2.)] + [frame(0., math.radians(120)) for _ in range(12)] + [frame(2.)]
        result = p.pose_metrics(frames, [[p.FORWARD, p.STOP] for _ in frames[1:]])
        self.assertAlmostEqual(result['max_body_tilt_degrees'][0], 120.)
        self.assertEqual(result['held_throttle_low_speed_episodes'][0], [{'first': 2, 'last': 13, 'samples': 12}])
        self.assertEqual(result['held_throttle_low_speed_episodes'][1], [])
        self.assertIn('not a physical cause', result['stall_threshold_scope'])


if __name__ == '__main__':
    unittest.main()
