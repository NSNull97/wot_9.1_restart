import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('full_test_stand', ROOT / 'tools' / 'full_test_stand.py')
stand = importlib.util.module_from_spec(spec)
spec.loader.exec_module(stand)


class RebaseTests(unittest.TestCase):
    MAPPING = [(Path(r'D:\other\local\stands\s1'), Path(r'D:\WoT\local\stands\new')),
               (Path(r'D:\other\local'), Path(r'D:\WoT\local'))]

    def test_specific_stand_prefix_wins_and_separator_is_kept(self):
        value = {'db': 'D:/other/local/stands/s1/game.sqlite',
                 'root': 'D:\\other\\local',
                 'nested': [{'path': 'd:\\OTHER\\local\\evidence\\x.json'}],
                 'port': 3692, 'name': 'D:/elsewhere/file'}
        self.assertEqual(stand.rebase(value, self.MAPPING), {
            'db': 'D:/WoT/local/stands/new/game.sqlite',
            'root': 'D:\\WoT\\local',
            'nested': [{'path': 'D:\\WoT\\local\\evidence\\x.json'}],
            'port': 3692, 'name': 'D:/elsewhere/file'})

    def test_pinned_files_finds_only_exact_path_sha_pairs(self):
        manifest = {'catalog': {'path': 'a', 'sha256': '1'}, 'profiles': [
            {'kind': 'ms1', 'pool': {'path': 'b', 'sha256': '2'}, 'geometry': {'path': 'c', 'sha256': '3', 'x': 1}}]}
        self.assertEqual([pin['path'] for pin in stand.pinned_files(manifest)], ['a', 'b'])


class BattleMapTests(unittest.TestCase):
    """MAPS-01 `map` command: switch a stopped stand's battle to a registry map."""
    import json as _json
    import os as _os
    import shutil as _shutil
    import tempfile as _tempfile
    LOCAL = (stand.LOCAL / 'stands').resolve().parent if (stand.LOCAL / 'stands').exists() else None
    FINAL = (LOCAL / 'evidence/20261020-maps01/final01') if LOCAL else None
    SOURCE = (LOCAL / 'stands/maps01-check-01/battle-profiles.before-02_malinovka.json') if LOCAL else None
    ALLOWED = {'map', 'terrain', 'obstacles', 'spawn_origin', 'spawn_yaw', 'bounds_xz'}

    def test_live_receipt_refuses(self):
        with self._tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            (directory / 'gateway-process.json').write_text('{}')
            with self.assertRaises(ValueError):
                stand.stand_stopped(directory)
            (directory / 'gateway-process.json').unlink()
            stand.stand_stopped(directory)

    def test_stand_outside_local_stands_refuses(self):
        class Args:
            stand = str(ROOT)
            package = catalog = str(ROOT)
            team = 'team1'
        with self.assertRaises(ValueError):
            stand.battle_map(Args)

    def test_real_stand_switch_keeps_accepted_entries_and_vehicle_physics(self):
        if not (self.SOURCE and self.SOURCE.is_file() and (self.FINAL / 'packages/02_malinovka/package.json').is_file()):
            self.skipTest('MAPS-01 local evidence absent: NOT_RUN')
        target = self.LOCAL / 'stands' / f'maps01-unit-{self._os.getpid()}'
        target.mkdir()
        try:
            self._shutil.copy2(self.SOURCE, target / 'battle-profiles.json')
            before = self._json.loads((target / 'battle-profiles.json').read_text(encoding='utf-8'))

            class Args:
                stand = str(target)
                package = str(self.FINAL / 'packages/02_malinovka')
                catalog = str(self.FINAL / 'catalogs/02_malinovka/manifest.json')
                team = 'team1'
            stand.battle_map(Args)
            after = self._json.loads((target / 'battle-profiles.json').read_text(encoding='utf-8'))
            self.assertEqual((after['map'], after['catalog']['sha256']), ('02_malinovka', stand.sha(Args.catalog)))
            self.assertEqual(after['shared_physics'], before['shared_physics'])
            for old, new in zip(before['profiles'], after['profiles']):
                self.assertEqual((old['kind'], old['geometry']), (new['kind'], new['geometry']))
                old_pool = self._json.loads(Path(old['pool']['path']).read_text(encoding='utf-8'))
                new_pool = self._json.loads(Path(new['pool']['path']).read_text(encoding='utf-8'))
                self.assertEqual(stand.sha(new['pool']['path']), new['pool']['sha256'])
                self.assertEqual(new_pool['maps'][0], old_pool['maps'][0])  # accepted Karelia entry unchanged
                self.assertEqual({k: v for k, v in new_pool.items() if k != 'maps'}, {k: v for k, v in old_pool.items() if k != 'maps'})
                template = [m for m in old_pool['maps'] if m['asset'] == '05_prohorovka'][0]
                derived = new_pool['maps'][1]
                self.assertEqual((derived['asset'], derived['arena_type_id']), ('02_malinovka', 2))
                a = self._json.loads(Path(template['config']).read_text(encoding='utf-8'))
                b = self._json.loads(Path(derived['config']).read_text(encoding='utf-8'))
                self.assertEqual({k for k in a if a[k] != b[k]} - self.ALLOWED, set())
            with self.assertRaises(ValueError):
                stand.battle_map(Args)  # already switched / map directory exists
        finally:
            self._shutil.rmtree(target)


if __name__ == '__main__':
    unittest.main()
