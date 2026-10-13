"""Read-only original EXE/string proof and additional-copy ownership boundary."""
import hashlib
import copy
from contextlib import contextmanager
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import shared_client_copy as module
from client_audit import config


class SharedCopyTests(unittest.TestCase):
    @contextmanager
    def copy_fixture(self, namespace=None):
        _, paths = config()
        original = (paths['original_client_root'] / 'WorldOfTanks.exe').read_bytes()
        parent = paths['local_artifacts_root'] / 'clients'
        parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='copy-namespace-test-', dir=parent) as scratch:
            root = Path(scratch).resolve()
            changed, edits = module.patched_exe(original, 'a', namespace)
            (root / 'WorldOfTanks.exe').write_bytes(changed)
            (root / 'WorldOfTanks.exe.p03f-backup').write_bytes(original)
            data = {'version': 1 if namespace is None else 2, 'scope': 'p03f-two-client-lab', 'slot': 'a',
                    'root': str(root), 'original_root': str(paths['original_client_root']),
                    'original_exe_sha256': module.ORIGINAL_EXE,
                    'patched_exe_sha256': hashlib.sha256(changed).hexdigest(), 'instance_mutex': edits[0]['after'],
                    'patches': edits, 'resource_copy_bytes': len(original), 'links_created': False,
                    'network_gameplay_code_modified': False, 'native_two_instances': 'NOT_RUN'}
            if namespace is not None:
                data['namespace'] = namespace
            yield root, paths, original, changed, data

    def write_marker(self, root, data):
        (root / module.MARKER).write_text(json.dumps(data), encoding='utf-8')

    def test_namespace_changes_only_two_source_pinned_strings_and_fits_each_slot(self):
        _, paths = config()
        original = (paths['original_client_root'] / 'WorldOfTanks.exe').read_bytes()
        hashes = []
        for slot in ('a', 'b'):
            legacy, legacy_edits = module.patched_exe(original, slot)
            self.assertEqual(module.patched_exe(original, slot, None), (legacy, legacy_edits))
            self.assertEqual(legacy_edits[0]['after'], f'sr_p03f_{slot}_mutex_')
            self.assertEqual(legacy_edits[1]['after'], f'sr_p03f_{slot}_wait____')
            changed, edits = module.patched_exe(original, slot, 'p06r')
            hashes.extend((hashlib.sha256(legacy).hexdigest(), hashlib.sha256(changed).hexdigest()))
            restored = bytearray(changed)
            for row, (offset, old) in zip(edits, module.STRINGS):
                self.assertEqual(row['offset'], offset)
                self.assertEqual(row['bytes'], 2 * (len(old) + 1))
                self.assertEqual(len(row['after']), len(old))
                self.assertEqual(changed[offset:offset + row['bytes']], (row['after'] + '\0').encode('utf-16le'))
                restored[offset:offset + row['bytes']] = (old + '\0').encode('utf-16le')
            self.assertEqual(edits[0]['after'], f'sr_p06r_{slot}_mutex_')
            self.assertEqual(edits[1]['after'], f'sr_p06r_{slot}_wait____')
            self.assertEqual(bytes(restored), original)
            self.assertEqual(len(changed), len(original))
        self.assertEqual(len(set(hashes)), 4)
        self.assertEqual(hashes[0], 'b627530f709b10b38c2da3b0ee57524e79b861e6911dbfc98824cffcec77da08')
        self.assertEqual(hashlib.sha256((paths['original_client_root'] / 'WorldOfTanks.exe').read_bytes()).hexdigest(), module.ORIGINAL_EXE)

    def test_namespace_rejects_wrong_length_non_ascii_uppercase_and_non_strings(self):
        _, paths = config()
        original = (paths['original_client_root'] / 'WorldOfTanks.exe').read_bytes()
        for namespace in ('', 'abc', 'abcde', 'P06r', 'p0_r', 'p0-r', 'p0 r', 'абвг', 'é123', 1234, True, [], {}):
            with self.subTest(namespace=namespace), self.assertRaises(ValueError):
                module.patched_exe(original, 'a', namespace)
        for namespace in ('0000', 'abcd', 'p06r'):
            self.assertEqual(module.checked_namespace(namespace), namespace)

    def test_checked_copy_validates_v1_and_v2_against_original_backup(self):
        for namespace in (None, 'p06r'):
            with self.subTest(namespace=namespace), self.copy_fixture(namespace) as (root, paths, _, _, data):
                self.write_marker(root, data)
                self.assertEqual(module.checked_copy(root, paths), (root, data))

    def test_manifest_cannot_authorize_arbitrary_exe_edit_by_updating_its_hash(self):
        for namespace in (None, 'p06r'):
            with self.subTest(namespace=namespace), self.copy_fixture(namespace) as (root, paths, _, changed, data):
                arbitrary = bytearray(changed); arbitrary[1024] ^= 1
                (root / 'WorldOfTanks.exe').write_bytes(arbitrary)
                data['patched_exe_sha256'] = hashlib.sha256(arbitrary).hexdigest()
                self.write_marker(root, data)
                with self.assertRaises(ValueError):
                    module.checked_copy(root, paths)

    def test_namespace_schema_names_and_patch_records_are_strict(self):
        with self.copy_fixture('p06r') as (root, paths, _, _, data):
            changed = []
            for key, value in (('version', 1), ('version', True), ('namespace', None), ('namespace', 'P06r'),
                               ('namespace', 'p09d'), ('instance_mutex', 'sr_p09d_a_mutex_'),
                               ('unexpected', True), ('links_created', True), ('root', 1)):
                row = copy.deepcopy(data); row[key] = value; changed.append(row)
            row = copy.deepcopy(data); del row['namespace']; changed.append(row)
            row = copy.deepcopy(data); row['patches'][1]['after'] = 'sr_p09d_a_wait____'; changed.append(row)
            row = copy.deepcopy(data); row['patches'][1]['offset'] = float(row['patches'][1]['offset']); changed.append(row)
            row = copy.deepcopy(data); row['patches'][1]['extra'] = 0; changed.append(row)
            for index, row in enumerate(changed):
                self.write_marker(root, row)
                with self.subTest(index=index), self.assertRaises(ValueError):
                    module.checked_copy(root, paths)
            self.write_marker(root, data)
            marker = root / module.MARKER
            marker.write_text(marker.read_text().replace('"version": 2', '"version": 2, "version": 2'), encoding='utf-8')
            with self.assertRaises(ValueError):
                module.checked_copy(root, paths)

    def test_modified_backup_is_rejected_even_with_valid_patched_exe(self):
        with self.copy_fixture('p06r') as (root, paths, original, _, data):
            self.write_marker(root, data)
            backup = bytearray(original); backup[1024] ^= 1
            (root / 'WorldOfTanks.exe.p03f-backup').write_bytes(backup)
            with self.assertRaises(ValueError):
                module.checked_copy(root, paths)

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
