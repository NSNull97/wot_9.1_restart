"""Parse-before-source production CLI regressions; no source catalog or SQL."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / 'tools/p10b_selection_loss_service.py'
READER = ROOT / 'tools/p10b_selection_loss.py'
READER_SHA = 'ad533816d4cf448c0e9cb4a4e6a98796859ee056d23a8eea5dd3299610a2eb62'


class SelectionLossCliTests(unittest.TestCase):
    def invoke(self, raw, *, oversize=False):
        # Tiny owned files are retained for audit; no cleanup of earlier data.
        cwd = Path(tempfile.mkdtemp(prefix='wot091-loss-cli-'))
        env = dict(os.environ)
        env.pop('PYTHONPATH', None)
        env['PYTHONDONTWRITEBYTECODE'] = '1'
        args = [sys.executable, '-B', '-X', 'utf8', str(CLI)]
        for name in ('database', 'bundle', 'original-root', 'shell-catalog', 'terminal-policy'):
            args += ['--' + name, str(cwd / ('missing-' + name))]
        args += ['--account-id', '11111111-1111-4111-8111-111111111111']
        result = subprocess.run(args, input=raw, capture_output=True, cwd=cwd, env=env, timeout=20)
        self.assertLessEqual(len(result.stdout) + len(result.stderr), 4096)
        (cwd / 'receipt.json').write_text(json.dumps(dict(
            schema='p10b-selection-loss-cli-parse.v1', cwd=str(cwd),
            returncode=result.returncode,
            input_sha256=hashlib.sha256(raw).hexdigest(),
            stdout_sha256=hashlib.sha256(result.stdout).hexdigest(),
            stderr_sha256=hashlib.sha256(result.stderr).hexdigest(),
            source_catalog_opened=False, database_opened=False,
            pythonpath_in_child=False), sort_keys=True) + '\n', encoding='utf-8')
        if oversize:
            # The existing bounded JSON reader rejects the byte limit outside
            # domain denials. Preserve fail-closed unavailable, no broad catch.
            self.assertEqual(result.returncode, 1)
            self.assertEqual(result.stdout, b'')
            self.assertEqual(result.stderr.decode('ascii').strip(), 'selection_loss_worker_invalid_or_unavailable')
        else:
            self.assertEqual(result.returncode, 0, result.stderr.decode('utf-8', 'replace'))
            self.assertEqual(result.stderr, b'')
            self.assertEqual(json.loads(result.stdout), {'error': 'selection_not_ready', 'code': 'INVALID_INPUT'})
        self.assertFalse(any(cwd.glob('missing-*')))

    def test_p10b_loss_cli_clean_environment_reaches_strict_parser(self):
        self.assertEqual(hashlib.sha256(READER.read_bytes()).hexdigest(), READER_SHA)
        self.invoke(b'{}')

    def test_p10b_loss_cli_oversize_refuses_before_source_or_sql(self):
        self.invoke(b' ' * 3073, oversize=True)


if __name__ == '__main__':
    unittest.main()
