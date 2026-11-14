"""Boundary tests on throwaway files; never open a running stand."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import content0_s5a_operator_onboard as tool

ACCOUNT = '12345678-1234-4234-8234-123456789abc'


class OnboardBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.stands = self.root / 'local' / 'stands'
        self.stand = self.stands / 'test-stand'
        self.stage = self.stand / 'operator-staging' / 'stage' / 'game.sqlite'
        self.stage.parent.mkdir(parents=True)
        (self.stand / 'backup-before-operator').mkdir()
        for file in (self.stage, self.stand / 'game.sqlite', self.stand / 'web.sqlite',
                     self.stand / 'backup-before-operator' / 'game.sqlite'):
            file.write_bytes(b'throwaway database placeholder')

    def tearDown(self): self.temp.cleanup()

    def test_rejects_foreign_stage_identity_and_existing_receipt(self):
        self.assertEqual(tool.checked_inputs(self.stand, ACCOUNT, self.stage, self.stands)[4], self.stage)
        outside = self.root / 'game.sqlite'; outside.write_bytes(b'outside')
        for stand, account, stage in ((self.stands, ACCOUNT, self.stage),
                                      (self.stand, ACCOUNT, outside),
                                      (self.stand, ACCOUNT.upper(), self.stage),
                                      (self.stand, 'invalid', self.stage),
                                      (self.stand, ACCOUNT, self.stand / 'game.sqlite')):
            with self.subTest(stand=stand, account=account, stage=stage):
                with self.assertRaises(ValueError): tool.checked_inputs(stand, account, stage, self.stands)
        (self.stand / 'operator-staging' / 'onboard-receipt.json').write_text('{}')
        with self.assertRaises(ValueError): tool.checked_inputs(self.stand, ACCOUNT, self.stage, self.stands)

    def test_wrong_backup_hash_rejects_before_any_database_write(self):
        receipt = {'schema': 'content0-s5a-snapshot.v1',
                   'databases': {'game.sqlite': {'sha256': '0' * 64}}}
        (self.stand / 'snapshot-receipt.json').write_text(json.dumps(receipt))
        files = [self.stage, self.stand / 'game.sqlite', self.stand / 'web.sqlite']
        before = [p.read_bytes() for p in files]
        args = ['--stand', str(self.stand), '--account', ACCOUNT, '--stage', str(self.stage),
                '--config', str(self.root / 'not-used.json'), '--original-root', str(self.root)]
        with patch.object(tool, 'ROOT', self.root), patch.dict(os.environ, {'WOT091_TEST_LAB': '1'}):
            with self.assertRaisesRegex(ValueError, 'backup differs'):
                tool.main(args)
        self.assertEqual(before, [p.read_bytes() for p in files])
        self.assertFalse((self.stand / 'operator-staging' / 'onboard-receipt.json').exists())


if __name__ == '__main__': unittest.main()
