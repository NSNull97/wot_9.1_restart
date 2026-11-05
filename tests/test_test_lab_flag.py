"""TESTVEH-01 stand flag (WOT091_TEST_LAB): each layer picks the main or the test_lab variant.

Every check runs in a child process so the flag is read the way a stand reads it
(once, from the environment of the process)."""
import json
import os
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'tools')]
import test_vehicles as tv  # noqa: E402

MAIN_CATALOG = '76afa3dcb003ffcc7a17c1b3a7c37aee39ccd4dbe05b1356bb64a3eb7686aefe'
TEST_LAB_CATALOG = 'ace7781a4beff55ad09765b5d9704c14920bde2089246b13072b0e4df5605204'


def run(argv, flag, cwd=ROOT):
    env = {k: v for k, v in os.environ.items() if k != tv.ENV}
    if flag is not None:
        env[tv.ENV] = flag
    return subprocess.run(argv, cwd=cwd, env=env, capture_output=True, text=True, timeout=300)


def python(code, flag):
    result = run([sys.executable, '-B', '-X', 'utf8', '-c', 'import sys; sys.path[:0]=["tools"]\n' + code], flag)
    if result.returncode:
        raise AssertionError(result.stderr[-800:])
    return json.loads(result.stdout)


class PythonLayer(unittest.TestCase):
    CODE = ('import json, battle_any, battle_any_data, catalog_v1_data, p04m_battle_profiles as p\n'
            'print(json.dumps([catalog_v1_data.CATALOG_SHA256, [v["kind"] for v in catalog_v1_data.VEHICLES][-1],'
            ' battle_any.data.TABLE_SHA256, len(battle_any.table()), p.CATALOG_SHA256]))')

    def test_main_mode_without_and_with_zero(self):
        for flag in (None, '0'):
            catalog, last, table, rows, research = python(self.CODE, flag)
            self.assertEqual((catalog, research, rows), (MAIN_CATALOG, tv.BASE_RESEARCH_SHA256, 374))
            self.assertNotEqual(last, 'ussr-T62A_T')

    def test_test_lab_mode(self):
        catalog, last, table, rows, research = python(self.CODE, '1')
        self.assertEqual((catalog, last, research, rows), (TEST_LAB_CATALOG, 'ussr-T62A_T', tv.TEST_LAB_RESEARCH_SHA256, 375))
        self.assertNotEqual(table, python(self.CODE, None)[2])

    def test_worker_catalogue_activation_follows_the_mode(self):
        code = 'import json, catalog_v1, catalog_v1_data as d\nprint(json.dumps(catalog_v1.activate(d.CATALOG_SHA256)))'
        self.assertEqual(python(code, None), MAIN_CATALOG)
        self.assertEqual(python(code, '1'), TEST_LAB_CATALOG)

    def test_bad_flag_refuses(self):
        result = run([sys.executable, '-B', '-c', 'import sys; sys.path[:0]=["tools"]; import catalog_v1_data'], 'yes')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('WOT091_TEST_LAB must be 0 or 1', result.stderr)


class GeneratedVariants(unittest.TestCase):
    def test_both_variants_are_current(self):
        for flag, catalog in ((None, MAIN_CATALOG), ('1', TEST_LAB_CATALOG)):
            table = run([sys.executable, '-B', '-X', 'utf8', 'tools/battle_any_profiles.py', 'check'], flag)
            self.assertEqual(json.loads(table.stdout)['status'], 'PASS', table.stdout)
            cat = run([sys.executable, '-B', '-X', 'utf8', 'tools/catalog_build.py', 'check'], flag)
            self.assertEqual(json.loads(cat.stdout)['catalog_sha256'], catalog, cat.stdout + cat.stderr)

    def test_main_variant_never_names_the_test_vehicle(self):
        for path in ('config/catalog/catalog.v1.json', 'config/catalog/battle_profiles.v1.json',
                     'config/catalog/server_profiles.v1.json', 'server/physics/Profiles/generated-definitions.json',
                     'server/gateway/src/shared/vehicle_catalog.rs', 'client_patch/catalog_v1_hints.py'):
            self.assertNotIn(b'T62A_T', (ROOT / path).read_bytes(), path)


@unittest.skipUnless(shutil.which('node'), 'node absent')
class NodeLayer(unittest.TestCase):
    CODE = ("const c=await import('./web/src/catalog-v1.mjs');const t=await import('./web/src/test-lab.mjs');"
            "console.log(JSON.stringify([c.CATALOG_SHA256,c.CATALOG_VEHICLES.at(-1).kind,t.RESEARCH_CATALOG_SHA256]))")

    def node(self, flag):
        result = run(['node', '--input-type=module', '-e', self.CODE], flag)
        if result.returncode:
            raise AssertionError(result.stderr[-800:])
        return json.loads(result.stdout)

    def test_modes(self):
        self.assertEqual(self.node(None)[0::2], [MAIN_CATALOG, tv.BASE_RESEARCH_SHA256])
        self.assertEqual(self.node('1'), [TEST_LAB_CATALOG, 'ussr-T62A_T', tv.TEST_LAB_RESEARCH_SHA256])
        bad = run(['node', '--input-type=module', '-e', self.CODE], 'true')
        self.assertNotEqual(bad.returncode, 0)


if __name__ == '__main__':
    unittest.main()
