"""Read-only original EXE/string proof and additional-copy ownership boundary."""
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import shared_client_copy as module
from client_audit import config


class SharedCopyTests(unittest.TestCase):
    def test_pinned_original_changes_only_the_two_names_at_known_offsets(self):
        _, paths = config()
        original = (paths['original_client_root'] / 'WorldOfTanks.exe').read_bytes()
        before = hashlib.sha256(original).hexdigest()
        outputs = []
        for slot in ('a', 'b'):
            changed, edits = module.patched_exe(original, slot)
            restored = bytearray(changed)
            for row in edits:
                offset = row['offset']
                restored[offset:offset + row['bytes']] = (row['before'] + '\0').encode('utf-16le')
            self.assertEqual(bytes(restored), original)
            self.assertEqual(len(changed), len(original))
            outputs.append(changed)
        self.assertNotEqual(outputs[0], outputs[1])
        self.assertEqual(before, module.ORIGINAL_EXE)
        with self.assertRaises(ValueError):
            module.patched_exe(original[:-1], 'a')
        with self.assertRaises(ValueError):
            module.patched_exe(original, 'c')
        self.assertEqual(hashlib.sha256((paths['original_client_root'] / 'WorldOfTanks.exe').read_bytes()).hexdigest(), before)

    def test_original_normal_research_and_parent_directories_cannot_be_selected(self):
        _, paths = config()
        for path in (paths['original_client_root'], paths['research_client_root'],
                     paths['local_artifacts_root'], paths['local_artifacts_root'] / 'clients',
                     paths['local_artifacts_root'] / 'clients/../../outside'):
            with self.assertRaises(ValueError):
                module.owned_copy(path, paths, False)

    def test_directory_without_copy_manifest_is_not_an_install_target(self):
        _, paths = config()
        parent = paths['local_artifacts_root'] / 'clients'
        parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='copy-guard-', dir=parent) as scratch:
            with self.assertRaises(FileNotFoundError):
                module.checked_copy(Path(scratch), paths)


if __name__ == '__main__':
    unittest.main()
