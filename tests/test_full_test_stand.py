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


if __name__ == '__main__':
    unittest.main()
