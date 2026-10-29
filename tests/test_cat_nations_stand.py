"""CAT-NATIONS stand switch: refusals before the first write.

The full switch/rollback run on a copy of stand -11 is recorded in
docs/plans/CAT_NATIONS_FIX.md (stands themselves are never touched by tests).
"""
import json
import os
from pathlib import Path
import shutil
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import cat_nations_stand as s


class Args:
    gateway = str(ROOT / 'local/build/none/sr-gateway.exe')
    pilot_sources = 'evidence'
    dry_run = True

    def __init__(self, stand):
        self.stand = str(stand)


@unittest.skipUnless((s.stand_tool.LOCAL / 'stands').is_dir(), 'local/stands absent: NOT_RUN')
class StandSwitchRefusals(unittest.TestCase):
    def setUp(self):
        self.stand = s.stand_tool.LOCAL / 'stands' / ('cat-nations-unit-%d' % os.getpid())
        self.stand.mkdir()
        self.addCleanup(shutil.rmtree, self.stand)
        for name in ('gateway.json', 'bridge.json'):
            (self.stand / name).write_text(json.dumps(dict(catalog=dict(version=1, sha256=s.OLD_CATALOG))))
        (self.stand / 'battle-profiles.json').write_text('{}')
        (self.stand / 'services.ps1').write_text("$gatewayExe = 'x'\n")

    def refused(self, command, text):
        with self.assertRaises(ValueError) as caught:
            command(Args(self.stand))
        self.assertIn(text, str(caught.exception))

    def test_stand_outside_local_stands_refuses(self):
        with self.assertRaises(ValueError):
            s.switch(Args(ROOT))
        with self.assertRaises(ValueError):
            s.rollback(Args(ROOT))

    def test_live_stand_refuses(self):
        for name in ('gateway-process.json', 'bridge-process.json', 'domain-process.json'):
            (self.stand / name).write_text('{}')
            self.refused(s.switch, 'live receipt')
            self.refused(s.rollback, 'live receipt')
            (self.stand / name).unlink()

    def test_stand_without_battle_any_refuses(self):
        self.refused(s.switch, 'not switched by full_test_stand.py battle-any')

    def test_switched_or_taken_names_refuse(self):
        (self.stand / 'battle-any-receipt.json').write_text('{}')
        (self.stand / s.RECEIPT).write_text('{}')
        self.refused(s.switch, 'already switched')
        (self.stand / s.RECEIPT).unlink()
        (self.stand / 'gateway.before-cat-nations.json').write_text('{}')
        self.refused(s.switch, 'saved names taken')

    def test_other_catalog_refuses(self):
        (self.stand / 'battle-any-receipt.json').write_text('{}')
        (self.stand / 'bridge.json').write_text(json.dumps(dict(catalog=dict(version=1, sha256='0' * 64))))
        self.refused(s.switch, 'bridge.json: catalog is not')

    def test_rollback_without_receipt_refuses(self):
        self.refused(s.rollback, 'stand was not switched by this tool')
        self.assertEqual(sorted(p.name for p in self.stand.iterdir()),
                         ['battle-profiles.json', 'bridge.json', 'gateway.json', 'services.ps1'])


if __name__ == '__main__':
    unittest.main()
