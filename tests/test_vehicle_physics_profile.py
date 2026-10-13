"""Real pinned #717 source import and stale/incorrect profile rejection.

Set WOT_PROJECT_ROOT to the configured local checkout when running in an
isolated worktree. No clients or workers are started by these tests.
"""
import copy
import json
import math
import os
from pathlib import Path
import sys
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'tools'))
import vehicle_physics_profile as v


class VehiclePhysicsProfileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(os.environ.get('WOT_PROJECT_ROOT', REPO)).resolve(strict=True)
        settings = v.read_json(cls.root / 'config/project.local.json', 65536)
        cls.local = Path(settings['paths']['local_artifacts_root']).resolve(strict=True)
        cls.original = Path(settings['paths']['original_client_root']).resolve(strict=True)
        cls.profile = v.build_profile(cls.original)
        cls.base = v.read_json(cls.root / 'local/evidence/20261012-p06p-prohorovka-01/boundary/near01/05_prohorovka-near-config.json')

    def test_actual_source_projection_exactly_matches_admitted_rust_bytes(self):
        raw = v.canonical(self.profile)
        self.assertEqual(v.sha(raw), v.PROFILE_SHA256)
        self.assertEqual(raw, (REPO / 'server/gateway/src/drive/worker/is7-physics-profile.json').read_bytes())
        v.validate_profile(self.profile)

    def test_source_dimensions_mass_and_power_are_not_ms1_mass_swap(self):
        p = self.profile['physics']
        self.assertEqual(p['mass_kg'], 68190)
        self.assertEqual(p['body_half_extents'], [1.6451992988586426, .5439350754022598, 3.6090246438980103])
        self.assertEqual(p['body_center_offset'], [0, 1.0385702341794967, .04841578006744385])
        self.assertEqual(p['engine_max_torque_nm'], 1050 * 735.5 / (2 * math.pi * 2500 / 60))
        self.assertEqual(p['max_forward_mps'], 59.6 * .27778)
        self.assertEqual(p['max_reverse_mps'], 15 * .27778)
        self.assertEqual(p['track_max_brake_torque'], 39500 * 9.81 * p['wheel_radius'] / 2)
        self.assertEqual(len(p['wheel_points']), 6)
        self.assertEqual([r[0] for r in p['wheel_points']], [-1.30381] * 3 + [1.30381] * 3)

    def test_projection_preserves_map_inputs_spawn_and_legacy_source(self):
        saved = copy.deepcopy(self.base)
        projected = v.project_config(self.base, self.profile)
        self.assertEqual(self.base, saved)
        for key in set(self.base) - set(v.PHYSICS_FIELDS) - {"version"}:
            self.assertEqual(projected[key], self.base[key])
        self.assertEqual(self.base['version'], 1)
        self.assertEqual(projected['version'], 2)
        self.assertEqual(projected['longitudinal_friction'], 1.2)
        self.assertEqual(projected['lateral_friction'], .4)
        self.assertEqual(projected['stationary_steering_ratio'], .2)
        self.assertEqual(self.base['mass_kg'], 4691)
        self.assertNotEqual(projected['body_half_extents'], self.base['body_half_extents'])

    def test_all_physics_changes_and_module_identity_are_unadmitted(self):
        for key in v.PHYSICS_FIELDS:
            p = copy.deepcopy(self.profile)
            if key in ('body_half_extents', 'body_center_offset'):
                p['physics'][key][0] += .01
            elif key == 'wheel_points':
                p['physics'][key][5][2] += .01
            else:
                p['physics'][key] += .01
            with self.subTest(field=key), self.assertRaisesRegex(ValueError, 'unadmitted'):
                v.validate_profile(p)
        for field, value in [('vehicle', 'ms1'), ('revision', 'is7-other-gun'), ('version', 2)]:
            p = copy.deepcopy(self.profile)
            p[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                v.validate_profile(p)

    def test_stale_or_edited_source_is_rejected_before_decode(self):
        with tempfile.TemporaryDirectory(prefix='p03m-source-negative-', dir=self.local) as folder:
            root = Path(folder).resolve()
            self.assertTrue(root.is_relative_to(self.local))
            source = root / 'source.xml'
            source.write_bytes(b'not-a-pinned-descriptor')
            with self.assertRaisesRegex(ValueError, 'source hash mismatch'):
                v.verified_file(root, 'source.xml', next(iter(v.SOURCE_PINS.values())))

    def test_duplicate_json_nonfinite_and_oversized_input_fail(self):
        with tempfile.TemporaryDirectory(prefix='p03m-json-negative-', dir=self.local) as folder:
            root = Path(folder).resolve()
            self.assertTrue(root.is_relative_to(self.local))
            file = root / 'bad.json'
            for raw in [b'{"x":1,"x":2}', b'{"x":NaN}', b'x' * 16385]:
                file.write_bytes(raw)
                with self.assertRaises(ValueError):
                    v.read_json(file)

    def test_map_schema_and_unadmitted_profile_are_rejected(self):
        for field, value in [('version', 2), ('map', 'unknown'), ('profile', 'public')]:
            c = copy.deepcopy(self.base)
            c[field] = value
            with self.assertRaises(ValueError):
                v.project_config(c, self.profile)
        c = copy.deepcopy(self.base)
        c['extra'] = 1
        with self.assertRaises(ValueError):
            v.project_config(c, self.profile)
        p = copy.deepcopy(self.profile)
        p['physics']['mass_kg'] = 4691
        with self.assertRaises(ValueError):
            v.project_config(self.base, p)

    def test_output_and_source_are_separate_owned_roots(self):
        with self.assertRaises(ValueError):
            v.owned(self.local, self.original / 'untouched.json')
        with self.assertRaises(ValueError):
            v.owned(self.local, self.local / '..' / 'untouched.json')


if __name__ == '__main__':
    unittest.main()
