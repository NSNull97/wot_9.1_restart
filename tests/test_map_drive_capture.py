"""Explicit bounded repeated-ride evidence; no native compatibility claim."""
import ast
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import manual_client_run as reader
import local_server


class CaptureProfileTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'packets.jsonl'
        self.profile = reader.DRIVE_CAPTURE_PROFILE
        self.header = dict(event='capture_started', profile=self.profile,
                           max_packets=48_000, max_wire_bytes=32 * 1024 * 1024)

    def write(self, rows):
        self.path.write_text(''.join(json.dumps(row) + '\n' for row in rows), encoding='utf8')

    def test_default_unchanged_and_extended_requires_named_profile(self):
        self.assertEqual(10_000, reader.capture_budget()['packets'])
        self.assertEqual(2 * 1024 * 1024, reader.capture_budget()['log'])
        self.write([self.header])
        self.assertEqual([], reader.manifest(self.path, self.profile)[1])
        with self.assertRaises(ValueError):
            reader.manifest(self.path)

    def test_header_missing_repeated_wrong_bounds_or_name_rejected(self):
        cases = [[], [self.header, self.header], [dict(self.header, profile='other')],
                 [dict(self.header, max_packets=48_001)],
                 [dict(self.header, max_packets=48_000.0)],
                 [dict(self.header, max_wire_bytes=33554432.0)],
                 [dict(self.header, max_wire_bytes=64 * 1024 * 1024)],
                 [dict(event='capture_started')]]
        for rows in cases:
            with self.subTest(rows=rows):
                self.write(rows)
                with self.assertRaises(ValueError):
                    reader.manifest(self.path, self.profile)

    def test_extended_still_checks_indices_paths_and_explicit_exhaustion(self):
        for packet in (dict(event='packet', index=1, bytes=1, file='packet-000001-client_to_server.bin'),
                       dict(event='packet', index=0, bytes=1, file='../outside.bin')):
            self.write([self.header, packet])
            with self.assertRaises(ValueError):
                reader.manifest(self.path, self.profile)
        self.write([self.header, dict(event='capture_limit')])
        self.assertIs(reader.manifest(self.path, self.profile)[2], True)

    def test_service_requires_capture_and_ordinary_map_pool(self):
        valid = dict(capture=True, capture_profile=self.profile)
        self.assertEqual(self.profile, local_server.native_capture_profile(SimpleNamespace(**valid), Path('pool')))
        for values, pool in ((dict(valid, capture=False), Path('pool')), (valid, None),
                             (dict(valid, capture_profile='unknown'), Path('pool'))):
            with self.subTest(values=values), self.assertRaises(ValueError):
                local_server.native_capture_profile(SimpleNamespace(**values), pool)
        state = dict(native_capture_profile=self.profile, native_wire_capture=True, map_drive_pool='own/pool')
        self.assertEqual(self.profile, reader.capture_profile(state))
        for changes in (dict(map_drive_pool=None), dict(native_wire_capture=False),
                        dict(native_capture_profile=True), dict(native_capture_profile='foreign')):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                reader.capture_profile(dict(state, **changes))

    def test_extended_packet_ceiling_is_finite(self):
        self.write([self.header] + [dict(event='packet', index=i, bytes=1,
                    file='packet-%06d-client_to_server.bin' % i) for i in range(48_001)])
        with self.assertRaisesRegex(ValueError, 'bounded budget'):
            reader.manifest(self.path, self.profile)


class NativeTraceBudgetTests(unittest.TestCase):
    def test_retry_scheduler_refuses_unbounded_or_foreign_delays(self):
        tree = ast.parse((ROOT / 'client_patch/sr_interactive.py').read_text(encoding='utf8'))
        node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'schedule_drive_observation')
        called = []
        observer = object()
        ns = dict(BigWorld=SimpleNamespace(callback=lambda *a: called.append(a)), observe=observer)
        exec(compile(ast.Module(body=[node], type_ignores=[]), '<owned-scheduler>', 'exec'), ns)
        for value in (0.1, 1.0):
            ns['schedule_drive_observation'](SimpleNamespace(next_observation_delay=lambda: value))
        self.assertEqual([(0.1, observer), (1.0, observer)], called)
        for value in (0, 1, True, -0.1, float('nan'), float('inf'), 0.0, 60.0, '0.1'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                ns['schedule_drive_observation'](SimpleNamespace(next_observation_delay=lambda: value))
        self.assertEqual(2, len(called))

    def test_only_explicit_phase_two_gets_larger_trace(self):
        tree = ast.parse((ROOT / 'client_patch/sr_interactive.py').read_text(encoding='utf8'))
        node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'observation_byte_limit')
        for enabled, control, phase, expected in ((True, True, 2, 64), (True, True, 1, 16),
                                                 (False, True, 2, 16), (True, False, 2, 16),
                                                 (True, True, None, 16), (True, True, 2.0, 16)):
            ns = dict(_settings=dict(enable_map_drive=enabled),
                      _control=dict(probe_map_drive_acceptance=control),
                      sys=SimpleNamespace(modules=dict(map_drive_acceptance=SimpleNamespace(PHASE_VERSION=phase))))
            # Compile only this repository's static function, never incoming data.
            exec(compile(ast.Module(body=[node], type_ignores=[]), '<owned-budget>', 'exec'), ns)
            self.assertEqual(expected * 1024 * 1024, ns['observation_byte_limit']())


if __name__ == '__main__':
    unittest.main()
