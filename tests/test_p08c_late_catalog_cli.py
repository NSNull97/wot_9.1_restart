"""LATE CLI catalog bootstrap in isolated interpreters; no game DB or native claim."""
import json
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
WORKER = ROOT / 'tools' / 'p08c_late_results_service.py'
CATALOG = '17dc1b3fa6059186e1bd4661a53409c267d8556471546e48ce44f8714d4376ea'
ARGS = ['--database', 'never-opened.sqlite', '--original-root', 'never-read',
        '--account-id', '12345678-1234-4234-8234-123456789000', '--shell-catalog', 'never-read',
        '--terminal-policy', 'never-read', '--ammo-rack-loss']


class LateCatalogCli(unittest.TestCase):
    def isolated(self, catalog=None):
        # Exercise actual CLI parsing/binding in a fresh interpreter; mock the
        # expensive business operation only. The live hybrid is separate.
        code = ("import sys; sys.path.insert(0, sys.argv.pop(1)); "
                "import catalog_v1 as c, p08c_late_results_service as w; "
                "w.load_catalog=lambda _:None; w.audit=lambda _:None; "
                "w.run=lambda args,operation,request:{'active':c.active()}; w.main()")
        args = [sys.executable, '-B', '-c', code, str(ROOT / 'tools'), *ARGS]
        if catalog is not None:
            args.extend(['--catalog-sha256', catalog])
        args.append('battle')
        return subprocess.run(args, input='{}', text=True, capture_output=True, cwd=ROOT, timeout=10)

    def test_legacy_and_pinned_catalog_each_start_in_a_fresh_process(self):
        legacy, catalog = self.isolated(), self.isolated(CATALOG)
        self.assertEqual(legacy.returncode, 0, legacy.stderr)
        self.assertEqual(json.loads(legacy.stdout), {'active': False})
        self.assertEqual(catalog.returncode, 0, catalog.stderr)
        self.assertEqual(json.loads(catalog.stdout), {'active': True})

    def test_bad_pin_refused_by_actual_cli_before_any_request_or_database_io(self):
        self.assertFalse((ROOT / 'never-opened.sqlite').exists())
        result = subprocess.run([sys.executable, '-B', str(WORKER), *ARGS, '--catalog-sha256', '0' * 64, 'battle'],
                                input='{}', text=True, capture_output=True, cwd=ROOT, timeout=10)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('CAT-01 catalog refused', result.stderr)
        self.assertEqual(result.stdout, '')
        self.assertFalse((ROOT / 'never-opened.sqlite').exists())


if __name__ == '__main__':
    unittest.main()
