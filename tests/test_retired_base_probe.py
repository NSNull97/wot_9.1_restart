"""Sender safety/unit controls and READ-ONLY analysis of accepted S packets.

Fake sockets never leave this process. The existing native corpus is read, not
replayed. These tests do not constitute T's network/native acceptance.
"""
import contextlib
import copy
import io
import json
from pathlib import Path
import socket
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from frozen_relogin_sources import historical_source_reader

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import retired_base_probe as probe


def temporary():
    parent = ROOT / 'local/evidence/20261005-p02-retired-base-replay/data/unit-temp'
    parent.mkdir(parents=True, exist_ok=True)
    return tempfile.TemporaryDirectory(dir=parent)


def cp(ready=10, capture=100, gateway=50):
    return {'sources': {'capture': {'last_index': capture}, 'gateway': {'lines': gateway},
                        'trace': {'last_ready_line': ready}}}


def candidate(kind, raw, index):
    return {'kind': kind, 'data': raw, 'row': {'index': index, 'file': 'unit-not-native.bin',
            'peer': '127.0.0.1:50428', 'elapsed_seconds': 1.0, 'bytes': len(raw), 'sha256': probe.sha(raw)}}


class FakeSocket:
    def __init__(self, observer=None, busy=False):
        self.observer, self.busy, self.bound, self.closed = observer, busy, None, False
        self.options, self.sent, self.binds = [], [], []

    def setsockopt(self, *args):
        self.options.append(args)

    def settimeout(self, timeout):
        self.timeout = timeout

    def bind(self, peer):
        self.binds.append(peer)
        if self.busy:
            raise OSError('UNIT occupied socket, no native/network operation')
        self.bound = peer

    def getsockname(self):
        return self.bound

    def close(self):
        self.closed = True

    def sendto(self, raw, destination):
        self.sent.append((raw, destination))
        if self.observer is not None:
            self.observer.pending = raw
        return len(raw)


class FakeObserver:
    def __init__(self):
        self.capture = SimpleNamespace(feedback=candidate('tokenless_feedback', b'UNIT-ACK', 10),
            logout=candidate('authenticated_logout', b'UNIT-LOGOUT', 20),
            attempts=[{'base_peer': '127.0.0.1:50428'}], decode=lambda row, raw: None)
        self.backend = SimpleNamespace(rejects=[])
        self.trace = SimpleNamespace(ready=True)
        self.pending, self.ready, self.index, self.gateway = None, 10, 100, 50
        self.fail_after_send, self.change_old_payload, self.duplicate_reject = False, False, False
        self.send_attempts, self.sent_datagrams = 0, 0

    def armed(self):
        return {'status': 'ARMED', 'unit_only': True}

    def update(self, decode=True):
        self.ready += 1
        if self.pending is None:
            return []
        raw, self.pending = self.pending, None
        self.index += 1
        self.gateway += 1
        if self.change_old_payload:
            raw += b'changed'
        self.backend.rejects.append({'line': self.gateway, 'start_offset': self.gateway * 10,
            'end_offset': self.gateway * 10 + 10, 'text': probe.REJECT_LINE})
        if self.duplicate_reject:
            self.backend.rejects.append(dict(self.backend.rejects[-1]))
        return [({'index': self.index, 'file': 'unit-ingress.bin', 'peer': '127.0.0.1:50428',
                 'direction': 'base_client_to_server', 'bytes': len(raw), 'sha256': probe.sha(raw), 'elapsed_seconds': 2.0}, raw)]

    def checkpoint(self, initial=False):
        if self.fail_after_send and self.backend.rejects:
            raise ValueError('secondary_trace_not_ready')
        return cp(self.ready, self.index, self.gateway)

    def validate_candidate(self, candidate):
        if getattr(self, 'candidate_changed', False):
            raise ValueError('original_candidate_file_changed')


class BoundsTests(unittest.TestCase):
    def test_endpoint_no_dns_wildcard_remote_or_service_port(self):
        for peer in ('localhost:50428', '0.0.0.0:50428', '127.0.0.2:50428', '8.8.8.8:53',
                     '127.0.0.1:20016', '127.0.0.1:0', '127.0.0.1:65536', ['127.0.0.1', 50428]):
            with self.subTest(peer=peer), self.assertRaises(ValueError):
                probe.endpoint(peer)

    def test_exact_socket_exclusive_no_reuse(self):
        fake = FakeSocket()
        result = probe.bind_source('127.0.0.1:50428', lambda *args: fake)
        self.assertIs(result, fake)
        self.assertEqual(fake.binds, [('127.0.0.1', 50428)])
        self.assertFalse(any(option[1] == socket.SO_REUSEADDR for option in fake.options))
        self.assertEqual(fake.timeout, 0.5)
        if hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
            self.assertIn((socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1), fake.options)

    def test_busy_old_port_no_fallback(self):
        fake = FakeSocket(busy=True)
        with self.assertRaises(OSError):
            probe.bind_source('127.0.0.1:50428', lambda *args: fake)
        self.assertEqual(fake.binds, [('127.0.0.1', 50428)])
        self.assertEqual(fake.sent, [])
        self.assertTrue(fake.closed)

    def test_invalid_or_unsupported_bind_never_creates_socket(self):
        with patch.object(probe.sys, 'platform', 'linux'), patch.object(probe.socket, 'socket') as factory:
            with self.assertRaises(ValueError):
                probe.bind_source('127.0.0.1:50428', factory)
            factory.assert_not_called()
        with patch.object(probe.socket, 'socket') as factory:
            with self.assertRaises(ValueError):
                probe.bind_source('localhost:50428', factory)
            factory.assert_not_called()

    def test_prefix_partial_line_hash_and_mutation(self):
        with temporary() as tmp:
            path = Path(tmp) / 'source.jsonl'
            path.write_bytes(b'one\ntw')
            prefix = probe.Prefix(path, 100, 20)
            self.assertEqual(len(prefix.update()), 1)
            self.assertEqual(prefix.checkpoint()['sha256'], probe.sha(b'one\n'))
            with path.open('ab') as stream:
                stream.write(b'o\n')
            self.assertEqual(prefix.update()[0]['start_offset'], 4)
            path.write_bytes(b'changed\n')
            with self.assertRaisesRegex(ValueError, 'append_only'):
                prefix.update()

    def test_prefix_line_and_file_bounds(self):
        with temporary() as tmp:
            path = Path(tmp) / 'source'
            path.write_bytes(b'x' * 21)
            with self.assertRaisesRegex(ValueError, 'partial_line'):
                probe.Prefix(path, 100, 20).update()
            path.write_bytes(b'x' * 21 + b'\n')
            with self.assertRaisesRegex(ValueError, 'source_line'):
                probe.Prefix(path, 100, 20).update()
            with self.assertRaises(ValueError):
                probe.Prefix(path, 10, 20).update()

    def test_json_duplicate_depth_nonfinite_and_boolean_identity(self):
        for raw in (b'{"x":1,"x":2}', b'[' * 22 + b'0' + b']' * 22, b'{"x":NaN}'):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                probe.json_value(raw)
        self.assertFalse(probe.same({'id': True}, {'id': 1}))

    def test_exact_redacted_control_schema(self):
        path = probe.S_CARD / 'switch02-prepare/native-process.json'
        actual = probe.json_file(path)['diagnostic_control']
        probe.control_metadata(actual)
        for key in ('password', 'sha256'):
            bad = dict(actual, **{key: 'UNIT forbidden'})
            with self.assertRaises(ValueError):
                probe.control_metadata(bad)
        for field, value in (('bytes', 8193), ('credentials_present', 1), ('plaintext_recorded', True)):
            with self.subTest(field=field), self.assertRaises(ValueError):
                probe.control_metadata(dict(actual, **{field: value}))

    def test_frame_classification_never_accepts_hidden_payload(self):
        # Explicit synthetic unit frame, not a native packet or crypto fixture.
        frame = {'flags': '0x448', 'sequence': 1, 'cumulative_ack': 1, 'body_hex': '',
                 'piggybacks': [], 'selective_acks': []}
        self.assertEqual(probe.classify_frame(frame, b'UNIT'), 'tokenless_feedback')
        for changed in (dict(frame, piggybacks=[frame]), dict(frame, body_hex='01'),
                        dict(frame, sequence=True), dict(frame, cumulative_ack=None)):
            self.assertIsNone(probe.classify_frame(changed, b'UNIT'))
        logout = dict(frame, flags='0x458', body_hex=(b'\x01UNIT\x0b\0').hex())
        self.assertEqual(probe.classify_frame(logout, b'UNIT'), 'authenticated_logout')
        self.assertIsNone(probe.classify_frame(dict(logout, piggybacks=[frame]), b'UNIT'))
        self.assertIsNone(probe.classify_frame(logout, b'ELSE'))

    def test_invalid_private_envelope_never_decrypts(self):
        with patch.object(probe.serialization, 'load_pem_private_key') as loader:
            with self.assertRaises(ValueError):
                probe.private_attempt(b'not a native packet', SimpleNamespace(key_size=1024), b'UNIT')
            loader.assert_not_called()


class SenderUnitTests(unittest.TestCase):
    def test_three_unchanged_sends_and_new_ready(self):
        observer = FakeObserver()
        fake = FakeSocket(observer)
        fake.bind(('127.0.0.1', 50428))
        with temporary() as tmp:
            result = probe.send_three(observer, Path(tmp), fake)
            self.assertEqual(result['status'], 'PASS')
            self.assertGreater(result['new_ready_line'], result['after_sends_ready_line'])
            self.assertEqual(fake.sent, [(b'UNIT-ACK', probe.DESTINATION), (b'UNIT-LOGOUT', probe.DESTINATION), (b'UNIT-LOGOUT', probe.DESTINATION)])
            self.assertEqual(len(list(Path(tmp).glob('send-??-after.json'))), 3)

    def test_loss_of_ready_after_first_send_stops(self):
        observer = FakeObserver()
        observer.fail_after_send = True
        fake = FakeSocket(observer)
        fake.bind(('127.0.0.1', 50428))
        with temporary() as tmp:
            with self.assertRaisesRegex(ValueError, 'secondary_trace_not_ready'):
                probe.send_three(observer, Path(tmp), fake)
            self.assertEqual(len(fake.sent), 1)
            self.assertEqual(len(list(Path(tmp).glob('send-??-sent.json'))), 1)
            self.assertFalse((Path(tmp) / 'send-02-before.json').exists())

    def test_changed_old_peer_packet_or_duplicate_reject_stops(self):
        for field in ('change_old_payload', 'duplicate_reject'):
            observer, fake = FakeObserver(), FakeSocket()
            fake.observer = observer
            setattr(observer, field, True)
            fake.bind(('127.0.0.1', 50428))
            with self.subTest(field=field), temporary() as tmp:
                with self.assertRaises(ValueError):
                    probe.send_three(observer, Path(tmp), fake)
                self.assertEqual(len(fake.sent), 1)

    def test_oversized_candidate_not_sent(self):
        observer = FakeObserver()
        observer.capture.feedback['data'] = b'UNIT' * 257
        fake = FakeSocket(observer)
        fake.bind(('127.0.0.1', 50428))
        with temporary() as tmp:
            with self.assertRaisesRegex(ValueError, 'send_byte_bound'):
                probe.send_three(observer, Path(tmp), fake)
            self.assertEqual(fake.sent, [])

    def test_original_source_file_changed_not_sent(self):
        observer = FakeObserver()
        observer.candidate_changed = True
        fake = FakeSocket(observer)
        fake.bind(('127.0.0.1', 50428))
        with temporary() as tmp, self.assertRaisesRegex(ValueError, 'original_candidate_file_changed'):
            probe.send_three(observer, Path(tmp), fake)
        self.assertEqual(fake.sent, [])

    def test_failed_preflight_does_not_create_socket(self):
        with temporary() as tmp, patch.object(probe, 'CARD', Path(tmp)), \
             patch.object(probe, 'Observer', side_effect=ValueError('invalid_preflight')), \
             patch.object(probe, 'bind_source') as bind, contextlib.redirect_stdout(io.StringIO()):
            args = SimpleNamespace(out=Path(tmp) / 'fresh', install='UNIT', service='UNIT', private_key='UNIT')
            self.assertEqual(probe.run(args), 1)
            bind.assert_not_called()
            result = probe.json_file(args.out / 'result.json')
            self.assertEqual(result['sends'], 0)
            self.assertEqual(result['gate'], 'invalid_preflight')

    def test_busy_port_reports_not_run_zero_sends(self):
        observer = FakeObserver()
        with temporary() as tmp, patch.object(probe, 'CARD', Path(tmp)), \
             patch.object(probe, 'Observer', return_value=observer), \
             patch.object(probe, 'bind_source', side_effect=OSError('UNIT busy')) as bind, \
             contextlib.redirect_stdout(io.StringIO()):
            args = SimpleNamespace(out=Path(tmp) / 'fresh', install='UNIT', service='UNIT', private_key='UNIT')
            self.assertEqual(probe.run(args), 2)
            bind.assert_called_once_with('127.0.0.1:50428')
            result = probe.json_file(args.out / 'result.json')
            self.assertEqual((result['status'], result['sends']), ('NOT_RUN', 0))

    def test_partial_failure_is_retained_no_private_exception(self):
        observer = FakeObserver()
        observer.fail_after_send = True
        fake = FakeSocket(observer)
        fake.bind(('127.0.0.1', 50428))
        with temporary() as tmp, patch.object(probe, 'CARD', Path(tmp)), \
             patch.object(probe, 'Observer', return_value=observer), patch.object(probe, 'bind_source', return_value=fake), \
             contextlib.redirect_stdout(io.StringIO()):
            args = SimpleNamespace(out=Path(tmp) / 'fresh', install='UNIT', service='UNIT', private_key='UNIT')
            self.assertEqual(probe.run(args), 1)
            result = probe.json_file(args.out / 'result.json')
            self.assertEqual((result['status'], result['sends']), ('FAIL', 1))
            self.assertTrue(fake.closed)
            self.assertNotIn('traceback', result)

    def test_evidence_write_failure_keeps_successful_send_count(self):
        observer = FakeObserver()
        fake = FakeSocket(observer)
        fake.bind(('127.0.0.1', 50428))
        original_save = probe.save_json

        def failing_save(path, value):
            if path.name == 'send-01-sent.json':
                raise OSError('UNIT failed evidence write')
            return original_save(path, value)

        with temporary() as tmp, patch.object(probe, 'CARD', Path(tmp)), patch.object(probe, 'Observer', return_value=observer), \
             patch.object(probe, 'bind_source', return_value=fake), patch.object(probe, 'save_json', side_effect=failing_save), \
             contextlib.redirect_stdout(io.StringIO()):
            args = SimpleNamespace(out=Path(tmp) / 'fresh', install='UNIT', service='UNIT', private_key='UNIT')
            self.assertEqual(probe.run(args), 1)
            result = probe.json_file(args.out / 'result.json')
            self.assertEqual((result['status'], result['sends'], result['attempted_sends']), ('FAIL', 1, 1))
            self.assertEqual(len(fake.sent), 1)
            self.assertFalse((args.out / 'send-01-sent.json').exists())

    def test_send_exception_records_attempt_without_retry(self):
        observer = FakeObserver()
        fake = FakeSocket(observer)
        fake.bind(('127.0.0.1', 50428))
        with temporary() as tmp, patch.object(probe, 'CARD', Path(tmp)), patch.object(probe, 'Observer', return_value=observer), \
             patch.object(probe, 'bind_source', return_value=fake), patch.object(fake, 'sendto', side_effect=TimeoutError) as send, \
             contextlib.redirect_stdout(io.StringIO()):
            args = SimpleNamespace(out=Path(tmp) / 'fresh', install='UNIT', service='UNIT', private_key='UNIT')
            self.assertEqual(probe.run(args), 1)
            result = probe.json_file(args.out / 'result.json')
            self.assertEqual((result['sends'], result['attempted_sends']), (0, 1))
            send.assert_called_once()


class ActualSourceRecheckUnitTests(unittest.TestCase):
    def test_candidate_exact_file_reread_rejects_tampering(self):
        with temporary() as tmp:
            path = Path(tmp) / 'unit-not-native.bin'
            path.write_bytes(b'UNIT-ACK')
            observer = object.__new__(probe.Observer)
            observer.capture = SimpleNamespace(folder=Path(tmp))
            c = candidate('tokenless_feedback', path.read_bytes(), 1)
            observer.validate_candidate(c)
            path.write_bytes(b'UNIT-BAD')
            with self.assertRaisesRegex(ValueError, 'original_candidate'):
                observer.validate_candidate(c)

    def test_live_server_rejects_changed_run_pid_configuration_and_exited_process(self):
        observer = object.__new__(probe.Observer)
        observer.runtime, observer.run = Path('UNIT-runtime'), Path('UNIT-runtime/run')
        observer.service_path, observer.service_raw = Path('UNIT-service'), b'UNIT-service'
        observer.gateway_raw, observer.gateway_pid = b'UNIT-gateway', 123
        observer.gateway_executable = Path(__file__)
        stat = observer.gateway_executable.stat()
        observer.gateway_file_stat = (stat.st_size, stat.st_mtime_ns)
        state = {'status': 'RUNNING', 'run_dir': str(observer.run), 'config': str(observer.service_path),
                 'processes': [{'role': 'gateway', 'pid': 123, 'executable_sha256': probe.GATEWAY_SHA}]}
        original_read = historical_source_reader(probe.read_limited)

        def read(path, limit):
            if path == observer.service_path:
                return observer.service_raw
            if path == observer.runtime / 'gateway.json':
                return observer.gateway_raw
            return original_read(path, limit)

        with patch.object(probe, 'json_file', return_value=state), patch.object(probe, 'process_image', return_value=observer.gateway_executable), \
             patch.object(probe, 'read_limited', side_effect=read):
            observer.live_server()
            for altered in (dict(state, status='STOPPED'), dict(state, run_dir='different'),
                            dict(state, processes=[dict(state['processes'][0], pid=456)])):
                with self.subTest(altered=altered), patch.object(probe, 'json_file', return_value=altered), self.assertRaises(ValueError):
                    observer.live_server()
            with patch.object(probe, 'process_image', side_effect=ValueError('native_process_exited')), self.assertRaises(ValueError):
                observer.live_server()
            with patch.object(probe, 'read_limited', return_value=b'changed'), self.assertRaisesRegex(ValueError, 'configuration'):
                observer.live_server()
            def changed_source(path, limit):
                if path == ROOT / 'tools/wg_probe/src/gateway091.rs':
                    return b'UNIT changed gateway source'
                return read(path, limit)

            with patch.object(probe, 'read_limited', side_effect=changed_source):
                with self.assertRaisesRegex(ValueError, 'server_configuration_changed'):
                    observer.live_server()


class AcceptedCorpusReadonlyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.install = probe.S_CARD / 'switch02-prepare'
        cls.capture_document = probe.json_file(cls.install / 'wire/capture.json', 8 * 1024 * 1024)
        cls.rows = cls.capture_document['packets']
        cls.private = probe.serialization.load_pem_private_key(probe.read_limited(ROOT / 'local/server/native-private.pem', 16384), None)
        cls.build = probe.read_limited(ROOT / 'local/server/client-digest.bin', 16)
        plan = probe.json_file(cls.install / 'install-plan.json')
        cls.trace_path = next(Path(plan['settings']['trace_dir']).glob('native-*.jsonl'))
        cls.trace_rows = [json.loads(line) for line in cls.trace_path.read_bytes().splitlines()]
        cls.accounts = next(r['expected_accounts'] for r in cls.trace_rows if r['event'] == 'account_switch_start')

    def test_current_corpus_source_selection_exact_no_socket(self):
        capture = probe.Capture(self.install / 'wire', self.private, self.build)
        seen = []
        with patch.object(probe.socket, 'socket') as network:
            for row in self.rows:
                if row['index'] >= 300:
                    break
                raw = probe.read_limited(self.install / 'wire' / row['file'], 4096)
                self.assertEqual(probe.sha(raw), row['sha256'])
                normalized = dict(row)
                capture.decode(normalized, raw)
                seen.append(normalized)
            network.assert_not_called()
        self.assertEqual(capture.feedback['row']['index'], 196)
        self.assertEqual(capture.logout['row']['index'], 279)
        self.assertEqual(capture.feedback['row']['peer'], '127.0.0.1:50428')
        self.assertEqual(capture.attempts[1]['base_peer'], '127.0.0.1:56298')
        capture.rows, capture.last_progress_at = seen, 500.0
        public = capture.context(500.01)
        self.assertTrue(public['session_cipher_key_equal'])
        self.assertFalse(public['inner_nonce_equal'])
        self.assertNotIn('key', public)
        self.assertNotIn('nonce', public)
        self.assertIsNotNone(capture.attempts[1]['token'])
        capture.rows[-1] = dict(capture.rows[-1], elapsed_seconds=capture.logout['row']['elapsed_seconds'] + 121)
        with self.assertRaisesRegex(ValueError, 'ttl'):
            capture.context(500.01)

    def make_trace(self, directory, end=None):
        rows = []
        for row in self.trace_rows:
            rows.append(row)
            if row['event'] == 'account_switch_state' and row.get('session_index') == 2:
                break
        if end is not None:
            rows.append(end)
        path = Path(directory) / 'trace.jsonl'
        path.write_bytes(b''.join(json.dumps(r, ensure_ascii=False).encode('utf8') + b'\n' for r in rows))
        trace = probe.Trace(path, self.accounts)
        trace.update(100.0)
        return trace

    def test_fresh_secondary_ready_actual_corpus_and_stale_guard(self):
        with temporary() as tmp:
            trace = self.make_trace(tmp)
            context = trace.context(100.1, initial=True)
            self.assertEqual(context['session_index'], 2)
            self.assertEqual(context['stable_seconds'], 0.0)
            with self.assertRaisesRegex(ValueError, 'stale'):
                trace.context(102.1)

    def test_secondary_disconnect_invalidates_previously_ready_sample(self):
        row = {'event': 'connection_callback', 'elapsed_seconds': 41.0, 'stage': 6, 'status': 'NOT_SET', 'native_connected': False}
        with temporary() as tmp:
            trace = self.make_trace(tmp, row)
            with self.assertRaisesRegex(ValueError, 'not_ready'):
                trace.context(100.1)

    def test_pending_trace_real_wrong_account_false_model_and_late_window(self):
        with temporary() as tmp:
            trace = self.make_trace(tmp)
            ready, line, at = trace.ready
            for change in ({'stable_seconds': 4.0},):
                trace.ready = (dict(ready, **change), line, at)
                with self.assertRaisesRegex(ValueError, 'window'):
                    trace.context(100.1, initial=True)
            trace.ready = (ready, line, at)
            hangar, line, at = trace.hangar
            trace.hangar = (dict(hangar, vehicle_model_loaded=False), line, at)
            with self.assertRaisesRegex(ValueError, 'not_ready'):
                trace.context(100.1)
        with temporary() as tmp:
            wrong = copy.deepcopy(self.accounts[1])
            wrong['database_id'] = 1
            row = next(copy.deepcopy(r) for r in self.trace_rows if r['event'] == 'account_switch_state' and r.get('session_index') == 2)
            row['state']['account'] = wrong
            with self.assertRaisesRegex(ValueError, 'secondary_native_state'):
                self.make_trace(tmp, row)

    def test_trace_error_is_not_silently_discarded(self):
        for event in ('python_exception', 'fini_enter'):
            row = {'event': event, 'elapsed_seconds': 41.0}
            with self.subTest(event=event), temporary() as tmp, self.assertRaisesRegex(ValueError, 'native_error'):
                self.make_trace(tmp, row)


if __name__ == '__main__':
    unittest.main()
