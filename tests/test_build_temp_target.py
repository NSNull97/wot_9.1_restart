"""Authored operator guard tests; no compiler, server, client or source mutation."""
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import uuid
import unittest
from unittest import mock

STAGE = Path(__file__).resolve().parent
BUILD_PATH = STAGE / 'server/build.py'
if not BUILD_PATH.is_file():
    BUILD_PATH = STAGE.parent / 'server/build.py'
REPOSITORY = next(p for p in STAGE.parents if (p / 'server/gateway/Cargo.toml').is_file())
spec = importlib.util.spec_from_file_location('candidate_build', BUILD_PATH)
build = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build)
RUN = REPOSITORY / 'local/test-runs/build-temp-target' / ('run-' + str(os.getpid()) + '-' + uuid.uuid4().hex)
RETAINED = []


class TempTargetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        RUN.mkdir(parents=True, exist_ok=False)

    def fresh(self, name):
        p = RUN / name
        p.mkdir(parents=True, exist_ok=False)
        return p

    def source(self, name, data=b'MZ' + bytes(range(256)) * 700):
        target = self.fresh(name)
        (target / 'debug').mkdir()
        source = target / 'debug/sr-gateway.exe'
        source.write_bytes(data)
        return target, source

    def test_only_explicit_canonical_selector(self):
        for component, legacy in [('physics', False), ('physics', True), ('gateway', True)]:
            with self.subTest(component=component, legacy=legacy):
                with self.assertRaisesRegex(ValueError, 'canonical gateway'):
                    build.check_temp_selector(component, legacy, True)
                build.check_temp_selector(component, legacy, False)
        build.check_temp_selector('gateway', False, True)

    def test_actual_cli_refuses_legacy_and_physics_before_any_out(self):
        import subprocess
        for component, extra in [('physics', []), ('gateway', ['--legacy'])]:
            out = RUN / ('cli-' + component)
            result = subprocess.run([os.sys.executable, '-B', '-X', 'utf8', str(BUILD_PATH),
                                     component, '--cargo-temp-target', *extra, '--out', str(out)],
                                    cwd=RUN, stdin=subprocess.DEVNULL, capture_output=True, timeout=10)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(b'canonical gateway without --legacy', result.stderr)
            self.assertFalse(out.exists())

    def test_default_output_boundary_and_existing_out_remain_strict(self):
        root = self.fresh('authored-project')
        (root / 'local/build/existing').mkdir(parents=True)
        expected = root / 'local/build/fresh'
        self.assertEqual(build.checked_output(root, 'local/build/fresh'), expected)
        self.assertFalse(expected.exists())
        for value in ('local/build', 'local/build/existing', 'local/elsewhere', '../escape'):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    build.checked_output(root, value)

    def test_real_default_system_temp_obeys_actual_drive_policy(self):
        out = self.fresh('actual-allocation')
        # The opt-in has meaning only across real drives. On a C-root/C-TEMP
        # workspace the expected real result is refusal BEFORE any allocation.
        # Positive artifact/receipt component cases use an explicit authored
        # volume identity in test_build_temp_reference; no actual build is claimed.
        if out.drive.lower() == Path(tempfile.gettempdir()).resolve().drive.lower():
            with mock.patch.object(build.tempfile, 'mkdtemp') as allocate:
                with self.assertRaisesRegex(ValueError, 'another drive'):
                    build.allocate_temp_target(out)
                allocate.assert_not_called()
            self.assertFalse((out / 'cargo-temp-target.json').exists())
            return
        target, receipt = build.allocate_temp_target(out)
        RETAINED.append(str(target))
        self.assertNotEqual(target.drive.lower(), out.drive.lower())
        self.assertEqual(target.parent, Path(tempfile.gettempdir()).resolve())
        self.assertTrue(target.name.startswith('wot091-cargo-'))
        self.assertEqual(json.loads((out / 'cargo-temp-target.json').read_text()), receipt)
        self.assertEqual(json.loads((target / 'wot091-build-origin.json').read_text())['output'], str(out))
        self.assertEqual(receipt['automatic_delete'], False)
        self.assertTrue(target.is_dir())

    def test_same_drive_default_temp_refuses_without_allocating(self):
        out = self.fresh('same-drive-output')
        default = self.fresh('same-drive-temp')
        with mock.patch.object(build.tempfile, 'gettempdir', return_value=str(default)), \
                mock.patch.object(build.tempfile, 'mkdtemp') as allocate:
            with self.assertRaisesRegex(ValueError, 'another drive'):
                build.allocate_temp_target(out)
            allocate.assert_not_called()
        self.assertFalse((out / 'cargo-temp-target.json').exists())

    def test_unc_default_temp_refuses_before_any_path_probe(self):
        out = self.fresh('unc-output')
        with mock.patch.object(build.tempfile, 'gettempdir', return_value='//authored-invalid-host/share/temp'), \
                mock.patch.object(build, 'no_reparse') as probe, \
                mock.patch.object(build.tempfile, 'mkdtemp') as allocate:
            with self.assertRaisesRegex(ValueError, 'local Windows drive'):
                build.allocate_temp_target(out)
            probe.assert_not_called()
            allocate.assert_not_called()

    def test_existing_windows_reparse_ancestor_is_rejected_without_following(self):
        # Read-only use of OS junctions. Do not manufacture new symlinks/junctions.
        choices = [Path(os.environ['USERPROFILE']) / 'Application Data',
                   Path(os.environ.get('SystemDrive', 'C:') + '/Documents and Settings')]
        actual = [p for p in choices if p.exists() and getattr(p.lstat(), 'st_file_attributes', 0) & 0x400]
        self.assertTrue(actual, 'This pinned Windows host must provide a real junction for this gate')
        for junction in actual:
            with self.assertRaisesRegex(ValueError, 'reparse'):
                build.no_reparse(junction / 'nonexistent-owned-build-test')

    def test_actual_copy_is_exclusive_equal_and_keeps_source(self):
        target, source = self.source('copy-source')
        out = self.fresh('copy-output')
        destination = out / 'target/debug/sr-gateway.exe'
        receipt = build.copy_verified_executable(source, destination, target)
        self.assertEqual(source.read_bytes(), destination.read_bytes())
        self.assertEqual(receipt['source_sha256_before'], receipt['output_sha256'])
        self.assertTrue(receipt['verified_equal'])
        original = destination.read_bytes()
        with self.assertRaisesRegex(ValueError, 'Fresh final'):
            build.copy_verified_executable(source, destination, target)
        self.assertEqual(destination.read_bytes(), original)
        self.assertTrue(source.is_file())

    def test_copy_detects_hash_corruption_and_retains_both_files(self):
        target, source = self.source('corrupt-source')
        out = self.fresh('corrupt-output')
        destination = out / 'target/debug/sr-gateway.exe'
        genuine = build.sha
        def corrupted_digest(path):
            return '0' * 64 if Path(path) == destination else genuine(path)
        with mock.patch.object(build, 'sha', side_effect=corrupted_digest):
            with self.assertRaisesRegex(ValueError, 'hash or size mismatch'):
                build.copy_verified_executable(source, destination, target)
        # Authored digest fault: no claim that an actual disk corruption was reproduced.
        self.assertTrue(source.exists())
        self.assertTrue(destination.exists())
        self.assertEqual(source.read_bytes(), destination.read_bytes())

    def test_copy_missing_or_oversize_or_non_pe_is_refused_before_output(self):
        target, source = self.source('bounded-source', b'MZabcdef')
        for name, data, limit in [('header', b'badheader', build.MAX_TEMP_EXECUTABLE_BYTES),
                                  ('oversize', b'MZabcdefgh', 8)]:
            source.write_bytes(data)
            out = self.fresh('invalid-' + name)
            destination = out / 'target/debug/sr-gateway.exe'
            with mock.patch.object(build, 'MAX_TEMP_EXECUTABLE_BYTES', limit):
                with self.assertRaises(ValueError):
                    build.copy_verified_executable(source, destination, target)
            self.assertFalse(destination.parent.exists())
        with self.assertRaisesRegex(ValueError, 'Only canonical'):
            build.copy_verified_executable(target / 'other.exe', RUN / 'missing/debug/sr-gateway.exe', target)

    def test_temp_receipt_excludes_ambient_credentials(self):
        env = {'CARGO_TARGET_DIR': 'C:/authored-target', 'CARGO_INCREMENTAL': '0',
               'TOKEN': 'authored-secret', 'PATH': 'authored-private-path', 'USERPROFILE': 'authored-private'}
        self.assertEqual(build.temp_environment(env), {'CARGO_TARGET_DIR': 'C:/authored-target', 'CARGO_INCREMENTAL': '0'})


if __name__ == '__main__':
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(TempTargetTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    receipt = {'schema': 'build-temp-target-tests.v1', 'tests_run': result.testsRun,
               'failures': len(result.failures), 'errors': len(result.errors),
               'test_fixtures': str(RUN), 'retained_system_temp_targets': RETAINED,
               'automatic_delete': False, 'actual_cross_drive_branch': 'NOT_RUN_SAME_DRIVE' if RUN.drive.lower()==Path(tempfile.gettempdir()).resolve().drive.lower() else 'REAL_ALLOCATION_ONLY_NO_BUILD', 'cargo': 'NOT_RUN', 'native': 'NOT_RUN',
               'authored_hash_fault': True, 'status': 'PASS' if result.wasSuccessful() else 'FAIL'}
    with (RUN / 'receipt.json').open('x', encoding='utf-8', newline='\n') as f:
        json.dump(receipt, f, indent=2)
        f.write('\n')
    raise SystemExit(not result.wasSuccessful())
