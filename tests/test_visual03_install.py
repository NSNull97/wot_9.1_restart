"""Isolated VISUAL-03 installer tests: no real client or game processes."""
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from tests.test_visual02_dds import header
from tools import visual03_install as install


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.client = self.root / 'client'
        self.profile = self.root / 'profile'
        self.evidence = self.root / 'evidence'
        self.batch = self.evidence / 'visual03-batch-20261114'
        self.manifest = self.batch / 'manifest.json'
        self.profile.mkdir(); self.batch.mkdir(parents=True)
        (self.client / 'res_mods/0.9.1/vehicles/russian/R13_KV-1s').mkdir(parents=True)
        (self.client / 'res/packages').mkdir(parents=True)
        self.existing = self.client / 'res_mods/0.9.1/vehicles/russian/R13_KV-1s/KV-1s_AM.dds'
        self.existing.write_bytes(b'accepted-kv1s-user-data')
        paths = ('<root><Paths><Path>' + self.profile.as_posix() + '</Path>'
                 '<Path>./res_mods/0.9.1</Path><Path>./res/packages/first.pkg</Path>'
                 '<Path>./res/packages/vehicles_russian.pkg</Path></Paths></root>').encode()
        (self.client / 'paths.xml').write_bytes(paths)
        with zipfile.ZipFile(self.client / 'res/packages/first.pkg', 'w') as z:
            z.writestr('unrelated/file.txt', b'other')
        pins = {}
        sources = {}
        outputs = []
        out_dir = self.batch / 'out'; out_dir.mkdir()
        for i, (name, fmt) in enumerate(zip(install.ASSETS, (b'DXT1', b'DXT3', b'DXT5'))):
            block_bytes = 8 if fmt == b'DXT1' else 16
            original = bytes(header(4, 4, fmt=fmt, mips=1)) + bytes(block_bytes)
            candidate = bytes(header(8, 8, fmt=fmt, mips=2)) + bytes(block_bytes * 4) + original[128:]
            sources[name] = original
            path = 'out/' + Path(name).name
            (self.batch / path).write_bytes(candidate)
            pins[name] = {'source_sha256': install.digest(original), 'format': fmt.decode(),
                          'width': 4, 'height': 4, 'source_mips': 1, 'output': path}
            outputs.append({'resource': name, 'source_sha256': install.digest(original),
                            'output': path, 'output_sha256': install.digest(candidate),
                            'source_mips': 1, 'output_mips': 2})
        with zipfile.ZipFile(self.client / 'res/packages/vehicles_russian.pkg', 'w') as z:
            for name, content in sources.items(): z.writestr(name, content)
        self.manifest.write_text(json.dumps({'schema':'wot091-visual03-batch.v1','assets':outputs}), encoding='utf-8')
        for name, value in [('CLIENT', self.client), ('PROFILE', self.profile), ('EVIDENCE_ROOT', self.evidence),
                            ('MANIFEST', self.manifest), ('PATHS_SHA256', install.digest(paths)), ('ASSETS', pins)]:
            patcher = mock.patch.object(install, name, value); patcher.start(); self.addCleanup(patcher.stop)
        patcher = mock.patch.object(install, '_process_paths', return_value=[])
        patcher.start(); self.addCleanup(patcher.stop)

    def target(self, resource):
        return self.client / 'res_mods/0.9.1' / resource

    def receipts(self, prefix):
        return list(self.batch.glob(prefix + '-*.json'))

    def assert_only_kv_remains(self):
        for name in install.ASSETS: self.assertFalse(self.target(name).exists(), name)
        self.assertEqual(self.existing.read_bytes(), b'accepted-kv1s-user-data')
        self.assertFalse(list((self.client / 'res_mods/0.9.1').rglob('*.visual03-*.tmp')))

    def test_install_and_reversible_rollback_preserve_other_files(self):
        receipt = install.install()
        self.assertEqual(json.loads(receipt.read_text(encoding='utf8'))['status'], 'PASS')
        for name in install.ASSETS: self.assertTrue(self.target(name).is_file())
        self.assertEqual(self.existing.read_bytes(), b'accepted-kv1s-user-data')
        rollback = install.rollback(receipt)
        data = json.loads(rollback.read_text(encoding='utf8'))
        self.assertEqual(data['status'], 'PASS')
        for item in data['assets']: self.assertTrue(Path(item['backup']).is_file())
        self.assert_only_kv_remains()

    def test_running_client_fails_closed_with_receipt(self):
        with mock.patch.object(install, '_process_paths', return_value=[str(self.client / 'WorldOfTanks.exe')]):
            with self.assertRaisesRegex(install.InstallError, 'running'): install.install()
        self.assert_only_kv_remains()
        self.assertEqual(json.loads(self.receipts('install')[0].read_text(encoding='utf8'))['status'], 'FAIL_ROLLED_BACK')

    def test_unrelated_client_process_does_not_block_target(self):
        with mock.patch.object(install, '_process_paths', return_value=[str(self.root / 'other' / 'WorldOfTanks.exe')]):
            install.ensure_client_stopped()

    def test_existing_override_never_overwritten_or_deleted(self):
        name = next(iter(install.ASSETS)); dst = self.target(name)
        dst.parent.mkdir(parents=True, exist_ok=True); dst.write_bytes(b'user-override')
        with self.assertRaisesRegex(install.InstallError, 'already exists'): install.install()
        self.assertEqual(dst.read_bytes(), b'user-override')
        self.assertEqual(self.existing.read_bytes(), b'accepted-kv1s-user-data')

    def test_profile_override_is_rejected(self):
        name = next(iter(install.ASSETS)); dst = self.profile / name
        dst.parent.mkdir(parents=True); dst.write_bytes(b'other-profile-data')
        with self.assertRaisesRegex(install.InstallError, 'profile override'): install.install()
        self.assertEqual(dst.read_bytes(), b'other-profile-data'); self.assert_only_kv_remains()

    def test_bad_candidate_mip_cannot_pass_even_if_manifest_hash_updated(self):
        doc = json.loads(self.manifest.read_text(encoding='utf8'))
        row = doc['assets'][0]; p = self.batch / row['output']; raw = bytearray(p.read_bytes()); raw[-1] ^= 1
        p.write_bytes(raw); row['output_sha256'] = install.digest(raw)
        self.manifest.write_text(json.dumps(doc), encoding='utf8')
        with self.assertRaisesRegex(install.InstallError, 'mip chain changed'): install.install()
        self.assert_only_kv_remains()

    def test_changed_alpha_cannot_pass_even_if_manifest_hash_updated(self):
        doc = json.loads(self.manifest.read_text(encoding='utf8'))
        row = doc['assets'][1]; p = self.batch / row['output']; raw = bytearray(p.read_bytes()); raw[128] = 0x0F
        p.write_bytes(raw); row['output_sha256'] = install.digest(raw)
        self.manifest.write_text(json.dumps(doc), encoding='utf8')
        with self.assertRaisesRegex(install.InstallError, 'top alpha is not exact'): install.install()
        self.assert_only_kv_remains()

    def test_partial_link_failure_rolls_back_own_files(self):
        real_link = install.os.link
        calls = [0]
        def flaky(source, target):
            calls[0] += 1
            if calls[0] == 2: raise OSError('synthetic link failure')
            return real_link(source, target)
        with mock.patch.object(install.os, 'link', side_effect=flaky):
            with self.assertRaisesRegex(install.InstallError, 'synthetic link failure'): install.install()
        self.assert_only_kv_remains()
        self.assertEqual(json.loads(self.receipts('install')[0].read_text(encoding='utf8'))['status'], 'FAIL_ROLLED_BACK')

    def test_nonempty_created_directory_is_recorded_not_deleted(self):
        marker = self.target(next(iter(install.ASSETS))).parent / 'user-added.txt'
        def fail_after_user_write(source, target):
            marker.write_bytes(b'user-data')
            raise OSError('synthetic link failure')
        with mock.patch.object(install.os, 'link', side_effect=fail_after_user_write):
            with self.assertRaises(install.InstallError): install.install()
        data = json.loads(self.receipts('install')[0].read_text(encoding='utf8'))
        self.assertEqual(data['status'], 'FAIL_ROLLED_BACK')
        self.assertIn(str(marker.parent), data['retained_nonempty_directories'])
        self.assertEqual(marker.read_bytes(), b'user-data')
        self.assertEqual(self.existing.read_bytes(), b'accepted-kv1s-user-data')

    def test_directory_cleanup_error_is_reported(self):
        original_rmdir = Path.rmdir
        def denied(path):
            if path.name == 'R11_MS-1': raise PermissionError('synthetic permission denial')
            return original_rmdir(path)
        with mock.patch.object(Path, 'rmdir', denied), mock.patch.object(install.os, 'link', side_effect=OSError('synthetic link failure')):
            with self.assertRaises(install.InstallError): install.install()
        data = json.loads(self.receipts('install')[0].read_text(encoding='utf8'))
        self.assertEqual(data['status'], 'FAIL_CLEANUP_INCOMPLETE')
        self.assertTrue(any('synthetic permission denial' in x for x in data['errors']))
        self.assertTrue((self.batch / 'visual03-operation.lock').exists())

    def test_keyboard_interrupt_during_second_link_cleans_up_and_propagates(self):
        real_link = install.os.link; calls = [0]
        def interrupted(source, target):
            calls[0] += 1
            if calls[0] == 2: raise KeyboardInterrupt()
            return real_link(source, target)
        with mock.patch.object(install.os, 'link', side_effect=interrupted):
            with self.assertRaises(KeyboardInterrupt): install.install()
        self.assert_only_kv_remains()
        self.assertEqual(json.loads(self.receipts('install')[0].read_text(encoding='utf8'))['status'], 'FAIL_ROLLED_BACK')
        self.assertFalse((self.batch / 'visual03-operation.lock').exists())

    def test_interrupt_after_successful_second_link_cleans_all_owned_targets(self):
        real_link = install.os.link; calls = [0]
        def interrupted(source, target):
            calls[0] += 1
            result = real_link(source, target)
            if calls[0] == 2: raise KeyboardInterrupt()
            return result
        with mock.patch.object(install.os, 'link', side_effect=interrupted):
            with self.assertRaises(KeyboardInterrupt): install.install()
        self.assert_only_kv_remains()
        self.assertEqual(json.loads(self.receipts('install')[0].read_text(encoding='utf8'))['status'], 'FAIL_ROLLED_BACK')
        self.assertFalse((self.batch / 'visual03-operation.lock').exists())

    def test_unknown_target_appearing_during_link_is_never_removed(self):
        target = self.target(next(iter(install.ASSETS)))
        def conflict(source, dst):
            Path(dst).write_bytes(b'user-new-override')
            raise OSError('simulated concurrent target')
        with mock.patch.object(install.os, 'link', side_effect=conflict):
            with self.assertRaises(install.InstallError): install.install()
        self.assertEqual(target.read_bytes(), b'user-new-override')
        data = json.loads(self.receipts('install')[0].read_text(encoding='utf8'))
        self.assertEqual(data['status'], 'FAIL_CLEANUP_INCOMPLETE')
        self.assertTrue((self.batch / 'visual03-operation.lock').exists())

    def test_interrupt_after_directory_creation_keeps_unknown_directory_and_lock(self):
        mkdir = Path.mkdir
        def interrupted(path, *args, **kwargs):
            result = mkdir(path, *args, **kwargs)
            if path.name == 'R11_MS-1': raise KeyboardInterrupt()
            return result
        with mock.patch.object(Path, 'mkdir', interrupted):
            with self.assertRaises(KeyboardInterrupt): install.install()
        directory = self.target(next(iter(install.ASSETS))).parent
        self.assertTrue(directory.is_dir())
        data = json.loads(self.receipts('install')[0].read_text(encoding='utf8'))
        self.assertEqual(data['status'], 'FAIL_CLEANUP_INCOMPLETE')
        self.assertTrue((self.batch / 'visual03-operation.lock').exists())
        self.assertEqual(self.existing.read_bytes(), b'accepted-kv1s-user-data')

    def test_interrupt_after_stage_creation_keeps_unknown_stage_and_lock(self):
        fstat = install.os.fstat; calls = [0]
        def interrupted(fd):
            calls[0] += 1
            if calls[0] == 3: raise KeyboardInterrupt()
            return fstat(fd)
        with mock.patch.object(install.os, 'fstat', side_effect=interrupted):
            with self.assertRaises(KeyboardInterrupt): install.install()
        data = json.loads(self.receipts('install')[0].read_text(encoding='utf8'))
        self.assertEqual(data['status'], 'FAIL_CLEANUP_INCOMPLETE')
        self.assertTrue((self.batch / 'visual03-operation.lock').exists())
        self.assertEqual(len(list((self.client / 'res_mods/0.9.1').rglob('*.visual03-*.tmp'))), 1)
        self.assertEqual(self.existing.read_bytes(), b'accepted-kv1s-user-data')

    def test_system_exit_during_second_rollback_rename_restores_and_propagates(self):
        receipt = install.install(); rename = install.os.rename; calls = [0]
        def interrupted(source, target):
            calls[0] += 1
            if calls[0] == 2: raise SystemExit(42)
            return rename(source, target)
        with mock.patch.object(install.os, 'rename', side_effect=interrupted):
            with self.assertRaises(SystemExit) as ctx: install.rollback(receipt)
        self.assertEqual(ctx.exception.code, 42)
        for name in install.ASSETS: self.assertTrue(self.target(name).is_file())
        self.assertEqual(json.loads(self.receipts('rollback')[0].read_text(encoding='utf8'))['status'], 'FAIL_NO_CHANGE')
        self.assertFalse((self.batch / 'visual03-operation.lock').exists())

    def test_interrupt_after_successful_second_rename_restores_all_sources(self):
        receipt = install.install(); rename = install.os.rename; calls = [0]
        def interrupted(source, target):
            calls[0] += 1
            result = rename(source, target)
            if calls[0] == 2: raise KeyboardInterrupt()
            return result
        with mock.patch.object(install.os, 'rename', side_effect=interrupted):
            with self.assertRaises(KeyboardInterrupt): install.rollback(receipt)
        for name in install.ASSETS: self.assertTrue(self.target(name).is_file())
        self.assertEqual(json.loads(self.receipts('rollback')[0].read_text(encoding='utf8'))['status'], 'FAIL_NO_CHANGE')
        self.assertFalse((self.batch / 'visual03-operation.lock').exists())

    def test_stale_lock_blocks_new_operation_and_names_receipt(self):
        path = self.batch / 'visual03-operation.lock'
        path.write_text('{"receipt":"unfinished-receipt.json"}', encoding='utf8')
        with self.assertRaisesRegex(install.InstallError, 'unfinished-receipt.json'):
            install.install()
        self.assertTrue(path.exists()); self.assert_only_kv_remains()

    def test_prepared_or_corrupt_receipt_blocks_new_operation(self):
        path = self.batch / ('install-' + 'a' * 32 + '.json')
        for content in ('{not-json', json.dumps({'schema': 'wot091-visual03-install-receipt.v1', 'status': 'PREPARED'})):
            with self.subTest(content=content):
                path.write_text(content, encoding='utf8')
                with self.assertRaisesRegex(install.InstallError, 'invalid receipt'):
                    install.install()
                self.assertTrue(path.exists()); self.assert_only_kv_remains()
                self.assertFalse((self.batch / 'visual03-operation.lock').exists())

    def test_modified_file_prevents_any_rollback(self):
        receipt = install.install(); names = list(install.ASSETS)
        self.target(names[1]).write_bytes(b'user-modified')
        with self.assertRaisesRegex(install.InstallError, 'modified'): install.rollback(receipt)
        self.assertTrue(self.target(names[0]).exists()); self.assertTrue(self.target(names[2]).exists())
        self.assertEqual(self.target(names[1]).read_bytes(), b'user-modified')
        self.assertEqual(self.existing.read_bytes(), b'accepted-kv1s-user-data')

    def test_identical_replacement_with_different_file_id_prevents_rollback(self):
        receipt = install.install(); names = list(install.ASSETS)
        target = self.target(names[1]); replacement = target.with_name('replacement.tmp')
        replacement.write_bytes(target.read_bytes()); install.os.replace(replacement, target)
        with self.assertRaisesRegex(install.InstallError, 'identity changed'):
            install.rollback(receipt)
        for name in names: self.assertTrue(self.target(name).exists())
        self.assertEqual(self.existing.read_bytes(), b'accepted-kv1s-user-data')

    def test_rollback_second_rename_failure_restores_first(self):
        receipt = install.install(); rename = install.os.rename; calls = [0]
        def flaky(source, target):
            calls[0] += 1
            if calls[0] == 2: raise OSError('synthetic rename failure')
            return rename(source, target)
        with mock.patch.object(install.os, 'rename', side_effect=flaky):
            with self.assertRaisesRegex(install.InstallError, 'synthetic rename failure'): install.rollback(receipt)
        for name in install.ASSETS: self.assertTrue(self.target(name).is_file())
        self.assertEqual(self.existing.read_bytes(), b'accepted-kv1s-user-data')
        self.assertEqual(json.loads(self.receipts('rollback')[0].read_text(encoding='utf8'))['status'], 'FAIL_NO_CHANGE')

    def test_earlier_package_shadow_blocks_install(self):
        name = next(iter(install.ASSETS))
        with zipfile.ZipFile(self.client / 'res/packages/first.pkg', 'a') as z: z.writestr(name, b'shadow')
        with self.assertRaisesRegex(install.InstallError, 'shadows'): install.install()
        self.assert_only_kv_remains()


if __name__ == '__main__': unittest.main()
