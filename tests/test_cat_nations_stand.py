"""CAT-NATIONS stand switch: refusals before the first write.

Only temporary synthetic stands are touched by these tests. A complete stand
switch and rollback on a copy of stand -11 remains NOT_RUN.
"""
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import cat_nations_stand as s
from tests.test_cat_nations_migrate import ACCOUNT, make


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


class PartialRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.stand = Path(self.temp.name).resolve()
        self.db = self.stand / 'game.sqlite'
        make(self.db)
        self.originals = {}
        for name in ('gateway.json', 'bridge.json', 'battle-profiles.json', 'services.ps1'):
            value = ('original ' + name).encode()
            (self.stand / name).write_bytes(value)
            self.originals[name] = value
        (self.stand / s.RESOURCES).mkdir()
        (self.stand / s.RESOURCES / 'old.txt').write_text('old')
        self.fixture = self.stand / 'fixtures' / ACCOUNT / 'p09d-r3'
        self.fixture.mkdir(parents=True)
        (self.fixture / 'old.txt').write_text(s.migrate.OLD)
        self.gateway = self.stand / 'sr-gateway.exe'
        self.gateway.write_bytes(b'gateway')
        self.facts = dict(present=list(self.originals), template={'profiles': [{'kind': 't26', 'pool': {'path': 'unused'}}]},
                          physics={}, gateway=self.gateway, sources=self.stand, kinds=[], database=self.db,
                          plan={'fixture_dirs': [str(self.fixture)]}, catalog='new')
        self.args = Args(self.stand)
        self.args.dry_run = False
        self.stop = mock.patch.object(s, 'stopped_stand', return_value=self.stand)
        self.stop.start()
        self.addCleanup(self.stop.stop)

    def test_failure_after_database_commit_and_fixture_move_can_be_rolled_back_and_retried(self):
        import battle_any_stand

        def generate(*args):
            output = args[-1]
            output.mkdir()
            (output / 'new.txt').write_text('new')
            return {'outputs': []}

        real_migrate = s.migrate.migrate
        def fail_after_commit(*args):
            real_migrate(self.db, self.stand, s.migrate.OLD, s.migrate.NEW)
            self.fixture.rename(self.fixture.with_name(self.fixture.name + s.migrate.MOVED_SUFFIX))
            raise OSError('simulated failure after commit')

        with mock.patch.object(s, 'switch_checks', return_value=self.facts), \
             mock.patch.object(battle_any_stand, 'generate', side_effect=generate), \
             mock.patch.object(s.migrate, 'migrate', side_effect=fail_after_commit):
            with self.assertRaisesRegex(OSError, 'after commit'):
                s.switch(self.args)
        self.assertTrue((self.stand / s.RECEIPT).is_file())
        self.assertEqual(s.migrate.verify(self.db, s.migrate.NEW)['status'], 'PASS')

        operation = json.loads((self.stand / s.RECEIPT).read_text())['operation']
        self.fixture.mkdir()
        collision = self.fixture.with_name(self.fixture.name + '.after-cat-nations-' + operation)
        collision.mkdir()
        with self.assertRaisesRegex(ValueError, 'fixture archive name taken'):
            s.rollback(self.args)
        self.assertEqual(s.migrate.verify(self.db, s.migrate.NEW)['status'], 'PASS')
        self.assertTrue((self.stand / s.RECEIPT).exists())
        collision.rmdir()

        # Interrupt rollback after DB and fixture restoration; it must remain retryable.
        real_copy = s.shutil.copy2
        def interrupted(src, dst, *args, **kwargs):
            if Path(dst).name == 'bridge.json':
                raise OSError('simulated interrupted rollback')
            return real_copy(src, dst, *args, **kwargs)
        with mock.patch.object(s.shutil, 'copy2', side_effect=interrupted):
            with self.assertRaisesRegex(OSError, 'interrupted rollback'):
                s.rollback(self.args)
        self.assertTrue((self.stand / s.RECEIPT).exists())
        s.rollback(self.args)
        self.assertFalse((self.stand / s.RECEIPT).exists())
        self.assertEqual(s.migrate.verify(self.db, s.migrate.OLD)['status'], 'PASS')
        self.assertEqual((self.fixture / 'old.txt').read_text(), s.migrate.OLD)
        self.assertEqual((self.stand / s.RESOURCES / 'old.txt').read_text(), 'old')
        for name, content in self.originals.items():
            self.assertEqual((self.stand / name).read_bytes(), content)
        kept = list(self.stand.glob('game.after-cat-nations-*.sqlite'))
        self.assertEqual(len(kept), 1)
        self.assertEqual(s.migrate.verify(kept[0], s.migrate.NEW)['status'], 'PASS')

    def test_successful_switch_and_rollback_with_real_migration(self):
        import battle_any_stand
        for name in ('gateway.json', 'bridge.json', 'battle-profiles.json'):
            self.originals[name] = b'{}'
            (self.stand / name).write_bytes(b'{}')
        self.originals['services.ps1'] = b"$gatewayExe = 'old'\n"
        (self.stand / 'services.ps1').write_bytes(self.originals['services.ps1'])

        def generate(*args):
            output = args[-1]
            output.mkdir()
            (output / 'battle-profiles-battle-any.json').write_text('{}')
            return {'outputs': []}
        with mock.patch.object(s, 'switch_checks', return_value=self.facts), \
             mock.patch.object(battle_any_stand, 'generate', side_effect=generate), \
             mock.patch.object(s.stand_tool, 'extend_catalog_shells', return_value={}):
            s.switch(self.args)
        self.assertEqual(s.migrate.verify(self.db, s.migrate.NEW)['status'], 'PASS')
        self.assertFalse(self.fixture.exists())
        s.rollback(self.args)
        self.assertEqual(s.migrate.verify(self.db, s.migrate.OLD)['status'], 'PASS')
        self.assertEqual((self.fixture / 'old.txt').read_text(), s.migrate.OLD)
        for name, content in self.originals.items():
            self.assertEqual((self.stand / name).read_bytes(), content)


if __name__ == '__main__':
    unittest.main()
