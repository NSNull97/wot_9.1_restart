"""Pinned P05B profile/export contract; never launches a client or worker."""
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
import tracked_handling_profile as h


class TrackedHandlingProfileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(os.environ.get('WOT_PROJECT_ROOT', REPO)).resolve(strict=True)
        _, cls.local, cls.original = h.context(cls.root)
        cls.ms1, cls.is7 = h.baseline_profiles(cls.root)
        cls.profiles = {kind: h.build_profile(cls.root, kind) for kind in ('ms1', 'is7')}
        cls.base_pool = h.legacy.read_json(cls.local / 'server/map-drive/pool.json')

    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='p05b-profile-', dir=self.local / 'build')
        self.addCleanup(temp.cleanup)
        self.folder = Path(temp.name).resolve()
        self.runtime = self.folder / 'bin'
        self.runtime.mkdir()
        self.exe = self.runtime / 'MapDriveWorker.exe'
        self.exe.write_bytes(b'bounded contract fixture: never executed')
        self.manifest = self.folder / 'artifacts.json'
        self.manifest_value = {'version': 1, 'files': [{'relative_path': self.exe.name,
            'bytes': self.exe.stat().st_size, 'sha256': h.sha(self.exe.read_bytes())}]}
        self.manifest.write_bytes(h.canonical(self.manifest_value))

    def source_pool(self, version=1):
        pool = copy.deepcopy(self.base_pool)
        pool['version'] = version
        if version == 2:
            path = self.folder / 'source-is7-profile.json'
            path.write_bytes(h.canonical(self.is7))
            pool['vehicle_profile'] = {'path': str(path), 'sha256': h.legacy.PROFILE_SHA256}
        for row in pool['maps']:
            config = h.legacy.read_json(Path(row['config']))
            if version == 2:
                config = h.legacy.project_config(config, self.is7)
            path = self.folder / (row['asset'] + '-source.json')
            raw = h.canonical(config)
            path.write_bytes(raw)
            row.update(config=str(path), config_sha256=h.sha(raw))
        path = self.folder / ('source-pool-' + str(version) + '.json')
        path.write_bytes(h.canonical(pool))
        return path, pool

    def test_original_bound_profiles_equal_exact_gateway_bytes(self):
        for kind, rate in [('ms1', 34), ('is7', 28)]:
            profile = self.profiles[kind]
            raw = h.canonical(profile)
            self.assertEqual(h.sha(raw), h.PROFILE_SHA256[kind])
            self.assertEqual(raw, (REPO / f'server/gateway/src/drive/worker/{kind}-handling-profile.json').read_bytes())
            self.assertEqual(profile['handling'], {'version': 1, 'policy': h.POLICY, 'max_yaw_rate_rad_s': math.radians(rate)})
            self.assertEqual(profile['physics']['lateral_friction'], 1.)
            expected = self.ms1 if kind == 'ms1' else self.is7['physics']
            for field in set(h.legacy.PHYSICS_FIELDS) - h.TRACTION_FIELDS:
                self.assertEqual(profile['physics'][field], expected[field])

    def test_profile_mass_identity_sources_and_policy_cannot_be_forged(self):
        for kind in self.profiles:
            p = self.profiles[kind]
            for key, value in [('vehicle', 'other'), ('revision', 'other'), ('version', 1), ('profile', 'historical_091')]:
                altered = copy.deepcopy(p)
                altered[key] = value
                with self.subTest(kind=kind, field=key), self.assertRaises(ValueError):
                    h.validate_profile(altered, kind)
            altered = copy.deepcopy(p)
            altered['sources'][h.PHYSICS_SOURCE] = '0' * 64
            with self.assertRaises(ValueError):
                h.validate_profile(altered, kind)
            with self.assertRaises(ValueError):
                h.validate_profile(p, 'is7' if kind == 'ms1' else 'ms1')

    def test_every_physical_config_field_is_bound_beyond_mass(self):
        for kind, profile in self.profiles.items():
            config = h.project_config(self.ms1, self.ms1, 1, profile, kind)
            for field in h.legacy.PHYSICS_FIELDS:
                altered = copy.deepcopy(config)
                if field in ('body_half_extents', 'body_center_offset'):
                    altered[field][0] += .01
                elif field == 'wheel_points':
                    altered[field][5][2] += .01
                else:
                    altered[field] += .01
                with self.subTest(kind=kind, field=field), self.assertRaisesRegex(ValueError, 'physics mismatch'):
                    h.verify_projection(altered, profile, kind)

    def test_handling_missing_extra_wrong_kind_and_boolean_fields_fail(self):
        for kind, profile in self.profiles.items():
            config = h.project_config(self.ms1, self.ms1, 1, profile, kind)
            other = self.profiles['is7' if kind == 'ms1' else 'ms1']['handling']
            for value in [{}, {'version': 1, 'policy': h.POLICY, 'max_yaw_rate_rad_s': .5},
                          dict(profile['handling'], version=True), dict(profile['handling'], policy='other'),
                          dict(profile['handling'], max_yaw_rate_rad_s=True), dict(profile['handling'], extra=0), other]:
                altered = copy.deepcopy(config)
                altered['handling'] = value
                with self.subTest(kind=kind, value=value), self.assertRaises(ValueError):
                    h.verify_projection(altered, profile, kind)

    def test_legacy_configuration_is_preserved_and_wrong_source_versions_reject(self):
        saved = copy.deepcopy(self.ms1)
        profile = self.profiles['is7']
        result = h.project_config(self.ms1, self.ms1, 1, profile, 'is7')
        self.assertEqual(saved, self.ms1)
        for field in ('terrain', 'obstacles', 'map', 'spawn_origin', 'spawn_yaw', 'bounds_xz'):
            self.assertEqual(result[field], self.ms1[field])
        for version in (2, 3, True):
            with self.assertRaises(ValueError):
                h.project_config(self.ms1, self.ms1, version, profile, 'is7')
        bad = copy.deepcopy(self.ms1)
        bad['mass_kg'] = 68190
        with self.assertRaisesRegex(ValueError, 'source physics mismatch'):
            h.project_config(bad, self.ms1, 1, profile, 'is7')

    def test_both_legacy_pool_versions_export_each_vehicle_and_preserve_inputs(self):
        for version in (1, 2):
            base, pool = self.source_pool(version)
            before = {Path(row['config']): Path(row['config']).read_bytes() for row in pool['maps']}
            before[base] = base.read_bytes()
            for kind in self.profiles:
                out = self.folder / f'export-{version}-{kind}'
                receipt = h.export(self.root, base, kind, self.exe, self.manifest, out)
                self.assertEqual(receipt['status'], 'PASS_PINNED_HANDLING_EXPORT_NOT_RUNTIME')
                new_pool = h.legacy.read_json(Path(receipt['pool_path']))
                self.assertEqual(new_pool['version'], 3)
                self.assertEqual(new_pool['vehicle_profile']['sha256'], h.PROFILE_SHA256[kind])
                self.assertEqual(new_pool['worker']['executable'], str(self.exe))
                for row, old_row in zip(new_pool['maps'], pool['maps']):
                    config = h.legacy.read_json(Path(row['config']))
                    original = h.legacy.read_json(Path(old_row['config']))
                    h.verify_projection(config, self.profiles[kind], kind)
                    for field in ('terrain', 'obstacles', 'spawn_origin', 'spawn_yaw', 'bounds_xz'):
                        self.assertEqual(config[field], original[field])
            self.assertTrue(all(path.read_bytes() == raw for path, raw in before.items()))

    def test_cross_version_profile_and_rehashed_source_mass_forgery_fail_before_output(self):
        base, pool = self.source_pool(2)
        pool['vehicle_profile']['sha256'] = h.PROFILE_SHA256['is7']
        base.write_bytes(h.canonical(pool))
        out = self.folder / 'rejected-source-profile'
        with self.assertRaisesRegex(ValueError, 'source profile reference mismatch'):
            h.export(self.root, base, 'is7', self.exe, self.manifest, out)
        self.assertFalse(out.exists())
        base, pool = self.source_pool(1)
        row = pool['maps'][0]
        config = h.legacy.read_json(Path(row['config']))
        config['mass_kg'] = 68190
        raw = h.canonical(config)
        Path(row['config']).write_bytes(raw)
        row['config_sha256'] = h.sha(raw)
        base.write_bytes(h.canonical(pool))
        with self.assertRaisesRegex(ValueError, 'source physics mismatch'):
            h.export(self.root, base, 'is7', self.exe, self.manifest, out)
        self.assertFalse(out.exists())

    def test_worker_manifest_is_complete_owned_and_exact_before_export(self):
        h.worker_reference(self.local, self.exe, self.manifest)
        extra = self.runtime / 'unlisted.dll'
        extra.write_bytes(b'unlisted')
        with self.assertRaisesRegex(ValueError, 'file set mismatch'):
            h.worker_reference(self.local, self.exe, self.manifest)
        extra.unlink()
        self.exe.write_bytes(b'x' * self.exe.stat().st_size)
        with self.assertRaisesRegex(ValueError, 'asset hash mismatch'):
            h.worker_reference(self.local, self.exe, self.manifest)

    def test_worker_manifest_traversal_duplicates_wrong_version_fail(self):
        for mode in ('traversal', 'duplicate', 'version'):
            manifest = copy.deepcopy(self.manifest_value)
            if mode == 'traversal':
                manifest['files'][0]['relative_path'] = '../MapDriveWorker.exe'
            elif mode == 'duplicate':
                manifest['files'].append(copy.deepcopy(manifest['files'][0]))
            else:
                manifest['version'] = True
            self.manifest.write_bytes(h.canonical(manifest))
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                h.worker_reference(self.local, self.exe, self.manifest)

    def test_export_requires_fresh_owned_destination_and_rejects_new_pool_as_source(self):
        base, _ = self.source_pool(1)
        out = self.folder / 'fresh'
        receipt = h.export(self.root, base, 'ms1', self.exe, self.manifest, out)
        with self.assertRaisesRegex(ValueError, 'fresh output'):
            h.export(self.root, base, 'ms1', self.exe, self.manifest, out)
        with self.assertRaisesRegex(ValueError, 'legacy1/2'):
            h.export(self.root, Path(receipt['pool_path']), 'ms1', self.exe, self.manifest, self.folder / 'new-source')
        with self.assertRaises(ValueError):
            h.export(self.root, base, 'ms1', self.exe, self.manifest, self.original / 'must-not-write')


if __name__ == '__main__':
    unittest.main()
