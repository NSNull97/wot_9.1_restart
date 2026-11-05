"""SHELL-01 step 5 comparison tool on synthetic meshes (no client)."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import armor_layers_native_compare as c  # noqa: E402

# Unit square plate at z=0 (two triangles, armor_1), and at z=1 (armor_2).
COMPONENT = {
    'name': 'Hull',
    'materials': [{'name': 'armor_1', 'kind': 1}, {'name': 'armor_2', 'kind': 2}],
    'vertices': [[0, 0, 0, 0, 0, 0, 0, 0], [1, 0, 0, 0, 0, 0, 0, 0], [1, 1, 0, 0, 0, 0, 0, 0], [0, 1, 0, 0, 0, 0, 0, 0],
                 [0, 0, 1, 0, 0, 0, 0, 0], [1, 0, 1, 0, 0, 0, 0, 0], [1, 1, 1, 0, 0, 0, 0, 0], [0, 1, 1, 0, 0, 0, 0, 0]],
    'triangles': [{'a': 0, 'b': 1, 'c': 2, 'material': 'armor_1', 'triangle_id': 0},
                  {'a': 0, 'b': 2, 'c': 3, 'material': 'armor_1', 'triangle_id': 1},
                  {'a': 4, 'b': 5, 'c': 6, 'material': 'armor_2', 'triangle_id': 2},
                  {'a': 4, 'b': 6, 'c': 7, 'material': 'armor_2', 'triangle_id': 3}],
}


class Geometry(unittest.TestCase):
    def test_all_crossings_in_order_with_kind_and_normal(self):
        hits = c.segment_hits(c.mesh(COMPONENT), (0.3, 0.6, -1.0), (0.3, 0.6, 2.0))
        self.assertEqual([round(h[0], 9) for h in hits], [1.0, 2.0])
        self.assertEqual([h[2] for h in hits], [1, 2])
        self.assertEqual([round(abs(h[1]), 9) for h in hits], [1.0, 1.0])

    def test_segment_end_limits_hits_and_miss_outside(self):
        self.assertEqual(len(c.segment_hits(c.mesh(COMPONENT), (0.3, 0.6, -1.0), (0.3, 0.6, 0.5))), 1)
        self.assertEqual(c.segment_hits(c.mesh(COMPONENT), (1.5, 0.6, -1.0), (1.5, 0.6, 2.0)), [])

    def test_degenerate_ids_are_excluded(self):
        part = dict(COMPONENT, excluded_degenerate_triangle_ids=[0, 1])
        self.assertEqual([h[2] for h in c.segment_hits(c.mesh(part), (0.3, 0.6, -1.0), (0.3, 0.6, 2.0))], [2])


class Verdicts(unittest.TestCase):
    PROJECT = [[1.0, -1.0, 1, 0], [2.0, -1.0, 2, 2]]

    def test_equal_and_each_mismatch(self):
        self.assertIsNone(c.compare_ray([[1.0004, 1.0, 1], [2.0, 1.0, 2]], self.PROJECT))
        self.assertEqual(c.compare_ray([[1.0, 1.0, 1]], self.PROJECT), 'count')
        self.assertEqual(c.compare_ray([[1.01, 1.0, 1], [2.0, 1.0, 2]], self.PROJECT), 'distance')
        self.assertEqual(c.compare_ray([[1.0, 1.0, 2], [2.0, 1.0, 2]], self.PROJECT), 'material')
        self.assertEqual(c.compare_ray([[1.0, 0.5, 1], [2.0, 1.0, 2]], self.PROJECT), 'angle')


class EndToEnd(unittest.TestCase):
    def test_report_from_trace_and_bundles(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / 'geo').mkdir(); (tmp / 'ch').mkdir()
            (tmp / 'geo' / 'ussr-X.json').write_text(json.dumps({'geometry': {'components': [COMPONENT, COMPONENT, COMPONENT]}}))
            (tmp / 'ch' / 'ussr-X.json').write_text(json.dumps({'component': dict(COMPONENT, name='Chassis')}))
            ray = {'start': [0.3, 0.6, -1.0], 'end': [0.3, 0.6, 2.0], 'hits': [[1.0, 1.0, 1], [2.0, 1.0, 2]]}
            bad = {'start': [0.3, 0.6, -1.0], 'end': [0.3, 0.6, 2.0], 'hits': [[1.0, 1.0, 1]]}
            lines = [{'event': 'armor_layers_rays', 'vehicle': 'ussr:X', 'component': 'hull', 'axis': 2, 'rays': [ray]},
                     {'event': 'armor_layers_rays', 'vehicle': 'ussr:X', 'component': 'chassis', 'axis': 2, 'rays': [ray, bad]},
                     {'event': 'armor_layers_calibers', 'vehicle': 'ussr:X', 'shells': []},
                     {'event': 'other'}]
            (tmp / 't.jsonl').write_text('\n'.join(json.dumps(x) for x in lines))
            report = c.compare(c.trace_records(tmp / 't.jsonl'), tmp / 'ch', tmp / 'geo')
            rows = {r['component']: r for r in report['components']}
            self.assertEqual(rows['hull']['verdicts']['equal'], 1)
            self.assertEqual((rows['chassis']['verdicts']['equal'], rows['chassis']['verdicts']['count']), (1, 1))
            self.assertEqual(rows['hull']['cos_sign'], {'same': 2, 'opposite': 0})
            self.assertFalse(report['all_equal'])
            self.assertEqual(len(report['calibers']), 1)

    def test_trace_without_records_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 't.jsonl'
            path.write_text('{"event": "x"}\n')
            with self.assertRaises(c.CompareError):
                c.trace_records(path)


if __name__ == '__main__':
    unittest.main()
