"""MAPS-01 map package exporter, registry and static native index.

Unit checks need nothing local. Source checks read the pinned original client
and recorded local evidence (WOT091_ROOT, default this checkout); they are
skipped — NOT_RUN, not PASS — when those inputs are absent.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import map_package as mp  # noqa: E402
import compound_destructible_catalog as cc  # noqa: E402

REGISTRY = ROOT / 'server/contracts/map_registry.json'
DATA_ROOT = Path(os.environ.get('WOT091_ROOT', ROOT))
NATIVE_EXPORTS = (
    ('01_karelia', 'evidence/20261012-p06o-destructible-import-01/runtime-a-oracle02/destructible-catalog-25340.json',
     'd9917eb5daf8c40aab13f2ce26c32f1dfcbcf6062b39cf12bbae142de6cc82e6'),
    ('05_prohorovka', 'evidence/20261012-p06p-prohorovka-01/runtime-a-oracle01/destructible-catalog-39152.json',
     '062c3fce8c2d7dd0ece94bfe6322a2a3b80f2a2d22be7de1906a8eb854f37e60'),
    ('05_prohorovka', 'evidence/20261013-p06r-compound-01/native-probe/runtime-a-fenceids01/destructible-catalog-46736.json',
     'ca420c2ca560457f87acc10b1449f262d0f8a1ec3c4eb163e9bde2ed1f6cc5ab'),
)
ACCEPTED_PROHOROVKA_CATALOG = ('evidence/20261013-p05b-tracked-handling-01/night-angular-export01/catalog/manifest.json',
                               '1dca4febb0bc4921263682f82b927e26c33248c5b837a885f075245adf948f99')


def sources_available():
    try:
        original, local = mp.configured_paths(DATA_ROOT)
    except (OSError, ValueError, KeyError):
        return False
    return (original / 'res/packages/01_karelia.pkg').is_file() and (local / ACCEPTED_PROHOROVKA_CATALOG[0]).is_file()


class UnitTests(unittest.TestCase):
    def test_checkerboard_matches_native_height_parity(self):
        rows = list(mp.checkerboard(3, 3))
        # Same cases as server/gateway/src/shared/terrain.rs indices(): (x ^ z) & 1.
        self.assertEqual(rows[:2], [(0, 3, 4), (0, 4, 1)])
        self.assertEqual(rows[2:4], [(1, 4, 2), (2, 4, 5)])
        self.assertEqual(len(rows), 8)

    def test_arena_points_accept_only_two_finite_numbers(self):
        self.assertEqual(mp.point2('430.100 1.500', 'p'), [430.1, 1.5])
        self.assertEqual(mp.point2([75.5, -391.5], 'p'), [75.5, -391.5])
        for bad in ('1', '1 2 3', [1.0], [float('nan'), 0.0], [1e9, 0.0], None):
            with self.assertRaises((mp.PackageError, ValueError)):
                mp.point2(bad, 'p')

    def test_map_names_are_original_asset_names_only(self):
        self.assertEqual(mp.map_name('02_malinovka'), '02_malinovka')
        for bad in ('malinovka', '2_malinovka', '02_Malinovka', '02_malinovka/../x', '02-malinovka', ''):
            with self.assertRaises(mp.PackageError):
                mp.map_name(bad)

    def test_verify_rejects_changed_missing_or_unsafe_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            (directory / 'arena.json').write_bytes(b'{}')
            package = {'version': 1, 'kind': 'wot091_map_package', 'map': '02_malinovka',
                       'files': {'arena.json': {'bytes': 2, 'sha256': hashlib.sha256(b'{}').hexdigest()}}}
            (directory / 'package.json').write_text(json.dumps(package), encoding='utf-8')
            mp.verify(directory)
            (directory / 'arena.json').write_bytes(b'[]')
            with self.assertRaises(mp.PackageError):
                mp.verify(directory)
            package['files'] = {'../arena.json': package['files']['arena.json']}
            (directory / 'package.json').write_text(json.dumps(package), encoding='utf-8')
            with self.assertRaises(mp.PackageError):
                mp.verify(directory)

    def test_registry_keeps_accepted_pins_and_orders(self):
        registry = json.loads(REGISTRY.read_text(encoding='utf-8'))
        self.assertEqual((registry['version'], registry['kind']), (1, 'wot091_server_map_registry'))
        maps = registry['maps']
        self.assertEqual([m['asset'] for m in maps[:2]], ['01_karelia', '05_prohorovka'])
        self.assertEqual(len({m['asset'] for m in maps}), len(maps))
        self.assertEqual(len({m['arena_type_id'] for m in maps}), len(maps))
        for entry in maps[:2]:
            pins = mp.REGRESSION_PINS[entry['asset']]
            self.assertEqual(entry['source'], 'legacy-accepted-evidence')
            self.assertEqual(entry['terrain']['vertices_sha256'], pins['terrain_vertices'])
            self.assertEqual(entry['terrain']['triangles_sha256'], pins['terrain_triangles'])
            self.assertEqual(entry['projectile']['vertices_sha256'], pins['projectile_vertices'])
            self.assertEqual(entry['projectile']['triangles_sha256'], pins['projectile_triangles'])
            self.assertEqual(entry['projectile']['flags_sha256'], pins['projectile_flags'])
            self.assertEqual(entry['physics']['manifest_sha256'], pins['physics_manifest'][1])
            self.assertEqual((entry['physics']['triangle_count'], entry['physics']['instance_count']),
                             (pins['physics_triangles_count'], pins['instances']))
        for entry in maps[2:]:
            self.assertEqual(set(entry['source']), {'package_relative', 'package_sha256'})
            self.assertTrue(entry['projectile']['manifest_relative'].startswith(entry['source']['package_relative'] + '/'))

    def test_fence_policy_list_equals_gateway_list(self):
        source = (ROOT / 'server/gateway/src/shared/fragiles.rs').read_text(encoding='utf-8')
        block = re.search(r'const FENCE_TOTAL_RESOURCES:\[&str;\d+\]=\[(.*?)\];', source, re.S).group(1)
        self.assertEqual(tuple(re.findall(r'"([^"]+)"', block)), cc.FENCE_TOTAL_RESOURCES)

    def test_static_index_rule_matches_gateway_rule(self):
        source = (ROOT / 'server/gateway/src/shared/fragiles.rs').read_text(encoding='utf-8')
        self.assertIn('STATIC_INDEX_RULE:&str="' + cc.STATIC_INDEX_RULE + '"', source)
        self.assertIn('"INFERRED_STATIC_RULE_NATIVE_CONFIRMATION_NOT_RUN"', source)


@unittest.skipUnless(sources_available(), 'pinned original client or local evidence absent: NOT_RUN')
class SourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original, cls.local = mp.configured_paths(DATA_ROOT)
        cls.out = mp.fresh_directory(cls.local / 'tests' / f'maps01-{os.getpid()}-{time.time_ns()}', cls.local)
        cls.packages = {name: mp.export(cls.original, name, cls.out / name) for name in ('01_karelia', '05_prohorovka')}

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.out)

    def test_port_reproduces_accepted_runtime_buffers_exactly(self):
        for name in self.packages:
            with self.subTest(map=name):
                result = mp.regression(self.out / name, self.local)
                self.assertEqual(result['status'], 'PASS', result['checks'])

    def test_static_native_index_equals_recorded_native_exports(self):
        for name, relative, digest in NATIVE_EXPORTS:
            with self.subTest(export=relative):
                result = mp.compare_native(self.out / name, self.local / relative, digest)
                self.assertEqual((result['status'], result['mismatched_chunks']), ('PASS', []))
                self.assertGreater(result['items'], 300)

    def test_export_is_deterministic(self):
        again = mp.export(self.original, '01_karelia', self.out / 'again-01_karelia')
        self.assertEqual(again['files'], self.packages['01_karelia']['files'])

    def test_static_catalog_reproduces_accepted_prohorovka_catalog(self):
        relative, digest = ACCEPTED_PROHOROVKA_CATALOG
        accepted = json.loads(mp.read_file(self.local / relative, 1024 * 1024))
        self.assertEqual(hashlib.sha256(mp.read_file(self.local / relative, 1024 * 1024)).hexdigest(), digest)
        inventory = cc.build_inventory(cc.tc.load_sources('05_prohorovka'))
        manifest_raw, _ = cc.join_static(inventory, self.out / '05_prohorovka')
        ours = json.loads(manifest_raw)
        self.assertEqual(ours.pop('native_index_source')['rule'], cc.STATIC_INDEX_RULE)
        accepted.pop('native_exports_sha256')
        self.assertEqual(ours, accepted)

    def test_wrong_package_is_rejected_by_regression_and_native_comparison(self):
        name, relative, digest = NATIVE_EXPORTS[0]
        with self.assertRaises(mp.PackageError):
            mp.compare_native(self.out / '05_prohorovka', self.local / relative, digest)
        with self.assertRaises(mp.PackageError):
            mp.compare_native(self.out / name, self.local / relative, '0' * 64)


if __name__ == '__main__':
    unittest.main()
