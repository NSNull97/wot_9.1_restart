"""Parser controls only. Two historical EXEs never prove one-process relogin."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from frozen_relogin_sources import historical_source_reader

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import verify_inprocess_relogin as v


class InprocessWireParserControls(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        base = ROOT / 'local/evidence/20261005-p02-hangar-windows'
        cls.installs = [base / (name + '-prepare') for name in ('windows01', 'windows02')]
        if not all((path / 'native-outcome.json').is_file() for path in cls.installs):
            raise unittest.SkipTest('Historical native parser corpus absent; NOT_RUN')
        parent = ROOT / 'local/evidence/20261005-p02-inprocess-relogin/wire'
        parent.mkdir(parents=True, exist_ok=True)
        cls.scratch = Path(tempfile.mkdtemp(prefix='parser-controls-', dir=parent))
        (cls.scratch / 'wire').mkdir()
        cls.outcomes = [v.crew.read_json(path / 'native-outcome.json') for path in cls.installs]
        cls.captures = [v.crew.read_json(path / 'wire/capture.json', 8 * 1024 * 1024) for path in cls.installs]
        cls.rows = cls.captures[0]['packets'] + cls.captures[1]['packets']
        cls.packets = []
        for install, capture in zip(cls.installs, cls.captures):
            for row in capture['packets']:
                raw = v.local_file(install / 'wire', row['file'], 4096)
                (cls.scratch / 'wire' / row['file']).write_bytes(raw)
                cls.packets.append(raw)
        cls.capture = {**cls.captures[0], 'packets': cls.rows,
                       'unit_test_only': 'Two different historical EXEs; not one-process acceptance evidence.'}
        cls.backend = b''.join(v.local_file(path, 'gateway-span.log', 8 * 1024 * 1024) for path in cls.installs)
        (cls.scratch / 'wire/capture.json').write_text(json.dumps(cls.capture), encoding='utf8')
        (cls.scratch / 'gateway-span.log').write_bytes(cls.backend)
        cls.outcome = {'gateway_run': cls.outcomes[0]['gateway_run'], 'wire_packets': len(cls.rows),
                       'gateway_log_span': {'file': 'gateway-span.log', 'sha256': v.digest(cls.backend),
                                            'start_offset': cls.outcomes[0]['gateway_log_span']['start_offset'],
                                            'end_offset': cls.outcomes[1]['gateway_log_span']['end_offset']}}
        (cls.scratch / 'unit-only.json').write_text(json.dumps({'native_acceptance': False,
            'source_client_pids': [o['client_pid'] for o in cls.outcomes], 'scope': 'Parser controls from historical closed native data'}), encoding='utf8')
        local_root = v.config()[1]['local_artifacts_root']
        exported, proof = v.crew.export_evidence(ROOT / 'local/evidence/20261005-p02-ms1-crew/native-ms1-crew-export01.json', local_root)
        cls.expected, _ = v.crew.crew_fixture(ROOT / 'local/server/fixtures/c5326cc1-8524-479c-8bba-72e973489c22/r3-catalog3', exported, proof, local_root)
        cls.password, _ = v.crew.identity(cls.expected, v.crew.DEFAULT_REG / 'registration.json',
                                        v.crew.DEFAULT_REG / 'test-credentials.json', 'operator_shared')
        cls.private = v.entry.serialization.load_pem_private_key((ROOT / 'local/server/native-private.pem').read_bytes(), None)
        cls.client_digest = (ROOT / 'local/server/client-digest.bin').read_bytes()
        cls.plan = v.crew.read_json(cls.installs[0] / 'install-plan.json', 1024 * 1024)
        runtime, _ = v.entry.runtime_rows(cls.installs[0], cls.plan, cls.outcomes[0], local_root)
        cls.runtime = runtime
        cls.ready_sample = next(row for row in runtime if row['event'] == 'native_hangar' and v.crew.hangar_ready(row, cls.expected))

    def captured(self, mutate=None):
        value = copy.deepcopy(self.capture)
        if mutate:
            mutate(value)
        original = v.local_file
        def reader(root, name, maximum):
            return json.dumps(value).encode('utf8') if name == 'capture.json' else original(root, name, maximum)
        with patch.object(v, 'local_file', side_effect=reader):
            return v.read_capture(self.scratch, self.outcome)

    def backend_variant(self, raw):
        outcome = copy.deepcopy(self.outcome)
        outcome['gateway_log_span']['sha256'] = v.digest(raw)
        outcome['gateway_log_span']['end_offset'] = outcome['gateway_log_span']['start_offset'] + len(raw)
        with patch.object(v, 'local_file', return_value=raw):
            return v.backend_ranges(self.scratch, outcome, self.expected)

    def test_frozen_protocol_sources(self):
        with patch.object(v, 'read_limited', side_effect=historical_source_reader(v.read_limited)):
            self.assertEqual(v.frozen_dependencies()['status'], 'PASS')

    def test_changed_archived_protocol_sources_are_rejected(self):
        reader = historical_source_reader(v.read_limited)
        for name in ('gateway091.rs', 'capture091.rs'):
            target = ROOT / 'tools/wg_probe/src' / name

            def changed(path, maximum):
                raw = reader(path, maximum)
                return raw + b'// UNIT mutation' if path == target else raw

            with self.subTest(source=name), patch.object(v, 'read_limited', side_effect=changed):
                with self.assertRaisesRegex(ValueError, 'frozen native gateway/capture source changed'):
                    v.frozen_dependencies()

    def test_saved_native_packets_partition_after_real_logout(self):
        rows, payloads, proof = self.captured()
        boundary, split = v.discover_boundary(rows, payloads, self.private, self.expected, self.password, self.client_digest)
        self.assertEqual(boundary, len(self.captures[0]['packets']))
        self.assertLess(split['first_disconnect']['offset'], boundary)
        self.assertEqual(proof['packet_hashes_checked'], 156)
        self.assertNotEqual(self.outcomes[0]['client_pid'], self.outcomes[1]['client_pid'])

    def test_independent_actual_attempts_disclose_no_private_values(self):
        result = v.native_attempt_transition(self.rows, self.packets, len(self.captures[0]['packets']), self.private,
                                             self.expected, self.password, self.client_digest)
        self.assertEqual(result['status'], 'PASS')
        self.assertFalse(result['private_values_or_hashes_logged'])
        self.assertFalse(result['session_cipher_key_equal'])
        self.assertNotIn('key', result)
        self.assertNotIn('nonce', result)
        self.assertNotIn('hardware', result)

    def attempt_vector(self):
        before = {'key': b'unit-key-16bytes!', 'nonce': b'old!', 'hardware': 'unit-hardware', 'ciphertext': b'unit-cipher-1',
                  'login_peer': '127.0.0.1:21000', 'base_peer': '127.0.0.1:21001', 'request_ids': [1]}
        current = {**before, 'nonce': b'new!', 'ciphertext': b'unit-cipher-2',
                   'login_peer': '127.0.0.1:21002', 'base_peer': '127.0.0.1:21003', 'request_ids': [2]}
        return before, current

    def test_same_key_requires_new_encrypted_nonce_and_both_new_peers(self):
        before, current = self.attempt_vector()
        report = v.compare_attempts(before, current)
        self.assertTrue(report['session_cipher_key_equal'])
        self.assertFalse(report['inner_nonce_equal'])

    def test_old_attempt_cannot_be_made_fresh_by_new_outer_request_id(self):
        before, current = self.attempt_vector()
        current['nonce'] = before['nonce']
        with self.assertRaisesRegex(ValueError, 'encrypted nonce'):
            v.compare_attempts(before, current)

    def test_both_retired_login_and_base_peers_are_excluded(self):
        before, current = self.attempt_vector()
        for new_side in ('login_peer', 'base_peer'):
            for retired_side in ('login_peer', 'base_peer'):
                with self.subTest(new=new_side, retired=retired_side), self.assertRaisesRegex(ValueError, 'peer belongs'):
                    v.compare_attempts(before, {**current, new_side: before[retired_side]})

    def test_fresh_key_does_not_require_distinct_nonce_peer_or_request(self):
        before, _ = self.attempt_vector()
        current = {**before, 'key': b'unit-fresh-key!!'}
        report = v.compare_attempts(before, current)
        self.assertFalse(report['session_cipher_key_equal'])
        self.assertTrue(report['inner_nonce_equal'])

    def test_hardware_tag_is_observation_not_freshness(self):
        before, current = self.attempt_vector()
        current['hardware'] = 'different-unit-hardware'
        self.assertFalse(v.compare_attempts(before, current)['hardware_session_tag_equal'])

    def test_packet_index_gap_is_not_ignored(self):
        def change(c):
            c['packets'][78]['index'] += 1
        with self.assertRaisesRegex(ValueError, 'gap/overlap'):
            self.captured(change)

    def test_packet_file_or_hash_cannot_be_substituted(self):
        for key, value in (('file', self.rows[0]['file']), ('sha256', '0' * 64)):
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.captured(lambda c: c['packets'][1].update({key: value}))

    def test_capture_limit_prevents_completeness_claim(self):
        with self.assertRaisesRegex(ValueError, 'complete'):
            self.captured(lambda c: c.update(limit_reached=True))

    def test_runner_packet_count_must_match_whole_source(self):
        with patch.dict(self.outcome, {'wire_packets': 155}), self.assertRaisesRegex(ValueError, 'packet count'):
            self.captured()

    def test_old_single_session_cannot_be_relabelled_as_relogin(self):
        n = len(self.captures[0]['packets'])
        with self.assertRaisesRegex(ValueError, 'two sequential'):
            v.discover_boundary(self.rows[:n], self.packets[:n], self.private, self.expected, self.password, self.client_digest)

    def test_second_auth_before_real_logout_is_not_sequential(self):
        boundary, proof = v.discover_boundary(self.rows, self.packets, self.private, self.expected, self.password, self.client_digest)
        cut = proof['first_disconnect']['offset']
        rows, packets = self.rows[:cut] + self.rows[boundary:], self.packets[:cut] + self.packets[boundary:]
        with self.assertRaises(ValueError):
            v.discover_boundary(rows, packets, self.private, self.expected, self.password, self.client_digest)

    def test_authenticated_reliable_disconnect_shape_only(self):
        token = b'1234'
        frame = {'body_hex': (b'\x01' + token + b'\x0b\0').hex(), 'flags': '0x458', 'sequence': 7, 'piggybacks': []}
        self.assertEqual(v.disconnect_frames(frame, token), [7])
        self.assertEqual(v.disconnect_frames(frame, b'5678'), [])
        frame['flags'] = '0x408'
        with self.assertRaisesRegex(ValueError, 'reliable'):
            v.disconnect_frames(frame, token)

    def test_backend_two_retirements_are_ordered_and_identity_bound(self):
        raw, bounds, proof = v.backend_ranges(self.scratch, self.outcome, self.expected)
        self.assertEqual(proof['status'], 'PASS')
        self.assertEqual(bounds[1], len(v.local_file(self.installs[0], 'gateway-span.log', 8 * 1024 * 1024)))
        self.assertFalse(proof['pending_literal_is_auth_worker_evidence'])
        self.assertNotEqual(proof['sessions'][0]['id'], proof['sessions'][1]['id'])
        self.assertLess(proof['sessions'][0]['fresh_auth_worker_line'], proof['sessions'][0]['pending_line'])
        self.assertLess(proof['sessions'][0]['closed_line'], proof['sessions'][1]['fresh_auth_worker_line'])

    def test_pending_duplicate_is_not_a_fresh_identity_worker(self):
        raw = self.backend.replace(b'AUTH_PENDING request_id=', b'AUTH_PENDING_DUPLICATE request_id=')
        with self.assertRaisesRegex(ValueError, 'independent fresh identity worker'):
            self.backend_variant(raw)

    def test_fresh_auth_worker_cannot_bind_to_another_native_request(self):
        _, _, proof = v.backend_ranges(self.scratch, self.outcome, self.expected)
        request = proof['sessions'][0]['fresh_auth_request']
        wire = {'status': 'PASS', 'login_requests': [{'request': request}], 'login_replies': [{'request': request}]}
        self.assertEqual(v.fresh_auth_binding(proof, 1, wire)['status'], 'PASS')
        wire['login_requests'][0]['request'] ^= 1
        with self.assertRaisesRegex(ValueError, 'does not match'):
            v.fresh_auth_binding(proof, 1, wire)

    def test_reused_server_identity_rejected_even_with_two_keys(self):
        _, _, proof = v.backend_ranges(self.scratch, self.outcome, self.expected)
        old, new = (str(r['id']).encode('ascii') for r in proof['sessions'])
        raw = self.backend.replace(b'id=' + new + b' ', b'id=' + old + b' ')
        with self.assertRaisesRegex(ValueError, 'identity was reused'):
            self.backend_variant(raw)

    def test_deadline_is_not_orderly_logoff(self):
        raw = self.backend.replace(b'reason=client_disconnect', b'reason=session_deadline', 1)
        with self.assertRaisesRegex(ValueError, 'orderly'):
            self.backend_variant(raw)

    def test_second_allocation_before_retirement_rejected(self):
        lines = self.backend.splitlines(keepends=True)
        first_close = next(i for i, line in enumerate(lines) if line.startswith(b'SESSION_CLOSED '))
        second_pending = [i for i, line in enumerate(lines) if line.startswith(b'SESSION_PENDING ')][1]
        lines[first_close], lines[second_pending] = lines[second_pending], lines[first_close]
        with self.assertRaisesRegex(ValueError, 'retired before'):
            self.backend_variant(b''.join(lines))

    def test_nonzero_retired_queue_is_recorded_not_misread_as_auth_worker(self):
        # Full acceptance still uses the frozen strict per-session ACK gate.
        _, _, proof = self.backend_variant(self.backend.replace(b'retired_pending=0', b'retired_pending=1', 1))
        self.assertEqual(proof['sessions'][0]['retired_reliable_pending'], 1)
        self.assertFalse(proof['pending_literal_is_auth_worker_evidence'])

    def test_derivation_preserves_all_bytes_and_native_indexes(self):
        rows, packets, capture = self.captured()
        raw, bounds, _ = v.backend_ranges(self.scratch, self.outcome, self.expected)
        target = Path(tempfile.mkdtemp(prefix='derived-', dir=self.scratch))
        parts, proof = v.derive_segments(target, rows, packets, 78, capture, raw, bounds, self.outcome)
        self.assertEqual(proof['packet_count'], 156)
        for n, (folder, outcome) in enumerate(parts):
            manifest = v.crew.read_json(folder / 'wire/capture.json', 8 * 1024 * 1024)
            self.assertEqual(manifest['packets'], self.captures[n]['packets'])
            self.assertFalse(manifest['derivation']['native_capture'])
            wire = v.entry.wire(folder, ROOT / 'local/server/native-private.pem', self.expected, self.password,
                                self.client_digest, dossier_cache=self.expected['dossier_cache'], cache_hints=True)
            self.assertEqual(wire['status'], 'PASS')
            self.assertEqual(v.entry.backend_binding(folder, outcome, wire, self.expected, v.config()[1]['local_artifacts_root'])['status'], 'PASS')

    def test_derivation_cannot_drop_a_packet_and_claim_full_source(self):
        rows, packets, capture = self.captured()
        raw, bounds, _ = v.backend_ranges(self.scratch, self.outcome, self.expected)
        target = Path(tempfile.mkdtemp(prefix='invalid-derive-', dir=self.scratch))
        with self.assertRaisesRegex(ValueError, 'lost/reordered'):
            v.derive_segments(target, rows[:-1], packets[:-1], 78, capture, raw, bounds, self.outcome)

    def ready_vector(self):
        rows = [dict(copy.deepcopy(self.ready_sample), elapsed_seconds=0.0),
                {'event': 'unit_interval_begin', 'elapsed_seconds': 0.001}]
        rows.extend(dict(copy.deepcopy(self.ready_sample), elapsed_seconds=float(i)) for i in range(1, 17))
        rows.append({'event': 'unit_interval_end', 'elapsed_seconds': 16.002})
        return rows

    def test_native_samples_not_marker_timer_prove_ready_interval(self):
        rows = self.ready_vector()
        proof = v.ready_interval(rows, 1, len(rows) - 1, self.expected)
        self.assertEqual(proof['observed_duration_seconds'], 16.0)
        self.assertEqual(proof['samples'], 17)

    def test_nonready_sample_resets_acceptance_even_if_marker_says_fifteen(self):
        rows = self.ready_vector()
        rows[10]['items_cache_synced'] = False
        with self.assertRaisesRegex(ValueError, 'non-ready'):
            v.ready_interval(rows, 1, len(rows) - 1, self.expected)

    def test_short_actual_interval_rejected(self):
        rows = self.ready_vector()[:15]
        rows.append({'event': 'unit_interval_end', 'elapsed_seconds': rows[-1]['elapsed_seconds'] + 0.001})
        with self.assertRaisesRegex(ValueError, 'shorter'):
            v.ready_interval(rows, 1, len(rows) - 1, self.expected)

    def test_sparse_samples_cannot_prove_continuous_readiness(self):
        rows = self.ready_vector()
        del rows[4:8]
        with self.assertRaisesRegex(ValueError, 'gap/order'):
            v.ready_interval(rows, 1, len(rows) - 1, self.expected)

    def test_expired_ready_state_does_not_prove_screenshot_phase(self):
        rows = self.ready_vector()
        rows[-1]['elapsed_seconds'] = 30
        with self.assertRaisesRegex(ValueError, 'stale'):
            v.ready_interval(rows, 1, len(rows) - 1, self.expected)

    def test_changed_resources_inside_ready_interval_rejected(self):
        rows = self.ready_vector()
        rows[10]['resources']['credits'] -= 1
        with self.assertRaisesRegex(ValueError, 'non-ready'):
            v.ready_interval(rows, 1, len(rows) - 1, self.expected)

    def test_original_repository_delete_and_logoff_sources_are_read(self):
        result = v.original_logoff_contracts()
        self.assertEqual(result['status'], 'PASS')
        repository_delete = next(r for r in result['sources'] if r['method'] == '_delAccountRepository')
        self.assertEqual(repository_delete['return_offset'], 71)
        constructors = {r['source_line']: r['return_offset'] for r in result['sources'] if r['method'] == '__init__'}
        self.assertEqual(constructors, {47: 674, 1640: 298})

    def test_historical_two_exes_cannot_supply_the_middle_runtime_transition(self):
        with self.assertRaisesRegex(ValueError, 'relogin_scenario_start'):
            v.runtime_transition(self.runtime, self.plan, self.outcomes[0])

    def test_historical_eleven_modules_are_not_current_twelve(self):
        with self.assertRaisesRegex(ValueError, 'twelve versioned modules'):
            v.compiled_sources(self.installs[0], self.plan, self.outcomes[0])

    def test_repeated_native_engine_init_rejected(self):
        rows = copy.deepcopy(self.runtime)
        rows.insert(0, copy.deepcopy(next(r for r in rows if r['event'] == 'init')))
        proof = v.process_runtime(self.installs[0], self.plan, self.outcomes[0], rows)
        self.assertEqual(proof['checks']['single_native_init']['status'], 'FAIL')
        self.assertEqual(proof['checks']['single_engine_cleanup']['status'], 'FAIL')

    def test_fini_between_sessions_cannot_be_hidden(self):
        rows = copy.deepcopy(self.runtime)
        rows.insert(3, copy.deepcopy(next(r for r in rows if r['event'] == 'fini')))
        proof = v.process_runtime(self.installs[0], self.plan, self.outcomes[0], rows)
        self.assertEqual(proof['checks']['single_engine_cleanup']['status'], 'FAIL')

    def test_same_native_owner_addresses_are_valid_context(self):
        value = {**v.limits.state_identity(self.expected), 'selected_inventory_id': 1, 'hangar_owner': 1234, 'crew_owner': 5678}
        self.assertEqual(v.context(value, self.expected), v.context(copy.deepcopy(value), self.expected))

    def test_context_boolean_ids_or_resource_change_rejected(self):
        base = {**v.limits.state_identity(self.expected), 'selected_inventory_id': 1, 'hangar_owner': 1234, 'crew_owner': 5678}
        for key, value in (('hangar_owner', True), ('selected_inventory_id', 2), ('resources', [0, 0, 0])):
            with self.subTest(key=key), self.assertRaises(ValueError):
                v.context({**base, key: value}, self.expected)

    def disconnected_vector(self):
        return {'native_connected': False, 'exact_disconnected': True, 'repository_absent': True, 'player_absent': True,
                'login_ready': True, 'class_name': 'LoginView', 'alias': 'login', 'flash_bound': True, 'owner_id': 1234}

    def test_complete_native_disconnected_view_metadata(self):
        value = self.disconnected_vector()
        self.assertEqual(v.disconnected_state(value), value)

    def test_status_not_connected_does_not_mean_exactly_disconnected(self):
        value = self.disconnected_vector()
        value['exact_disconnected'] = False
        with self.assertRaisesRegex(ValueError, 'exact_disconnected'):
            v.disconnected_state(value)

    def test_old_repository_or_player_invalidates_new_login(self):
        for field in ('repository_absent', 'player_absent'):
            with self.subTest(field=field), self.assertRaises(ValueError):
                v.disconnected_state({**self.disconnected_vector(), field: False})

    def test_disposed_or_wrong_view_cannot_be_a_login_boundary(self):
        for field, value in (('flash_bound', False), ('class_name', 'Hangar'), ('owner_id', True)):
            with self.subTest(field=field), self.assertRaises(ValueError):
                v.disconnected_state({**self.disconnected_vector(), field: value})

    def test_without_native_scenario_pixels_cannot_pass(self):
        with self.assertRaisesRegex(ValueError, 'complete two-session'):
            v.visual_review(self.installs[0], '0' * 64, {'status': 'FAIL'})

    def visual_vector(self):
        # Validator unit data only; these historical images are not relogin evidence.
        image = next(r['screenshot'] for r in self.runtime if r['event'] == 'windows_scenario_screenshot')
        images = [{'file': name, 'path': str(self.scratch / name), 'sha256': image['sha256']}
                  for name in ('unit_first.png', 'unit_second.png')]
        proof = {'status': 'PASS', 'images': images}
        review = {'version': 1, 'source': 'assistant_native_png_review', 'trace_sha256': 'unit-test-trace',
                  'images': [{**r, 'hangar_visible': True, 'ms1_visible': True, 'two_crew_visible': True,
                              'crew_names_and_levels_visible': True, 'resources_unchanged': True} for r in images]}
        return proof, review

    def check_visual(self, proof, review):
        with patch.object(Path, 'is_file', return_value=True), patch.object(v, 'read_limited', return_value=json.dumps(review).encode('utf8')):
            return v.visual_review(self.scratch, 'unit-test-trace', proof)

    def test_two_hash_bound_review_items_required(self):
        proof, review = self.visual_vector()
        self.assertEqual(self.check_visual(proof, review)['status'], 'PASS')
        review['images'].pop()
        with self.assertRaisesRegex(ValueError, 'two distinct'):
            self.check_visual(proof, review)

    def test_visual_hash_mismatch_rejected(self):
        proof, review = self.visual_vector()
        review['images'][1]['sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'hash/path'):
            self.check_visual(proof, review)

    def test_review_from_another_trace_rejected(self):
        proof, review = self.visual_vector()
        review['trace_sha256'] = 'another-trace'
        with self.assertRaisesRegex(ValueError, 'source/trace'):
            self.check_visual(proof, review)

    def test_same_basename_in_foreign_directory_is_not_exact_review(self):
        proof, review = self.visual_vector()
        review['images'][1]['file'] = str(self.scratch / 'wrong-directory' / proof['images'][1]['file'])
        with self.assertRaisesRegex(ValueError, 'hash/path'):
            self.check_visual(proof, review)

    def test_not_observed_crew_pixels_cannot_be_substituted_by_native_data(self):
        proof, review = self.visual_vector()
        review['images'][1]['two_crew_visible'] = False
        with self.assertRaisesRegex(ValueError, 'pixels failed'):
            self.check_visual(proof, review)

    def login_result_vector(self):
        return [{'event': 'unit_actual_callback'},
                {'event': 'relogin_scenario_login_result', 'version': 2, 'phase': 'waiting_hangar', 'session_index': 2,
                 'expected_session_index': 2, 'stage': 1, 'status': 'LOGGED_ON', 'source': 'original_ConnectionManager.connectionWatcher',
                 'callback_injected': False, 'handled_outside_callback': True},
                {'event': 'relogin_scenario_state', 'session_index': 2}]

    def test_passive_v2_result_after_original_callback(self):
        self.assertEqual(v.second_login_result(self.login_result_vector(), 2, 0)['status'], 'PASS')

    def test_v2_rejection_cannot_be_accepted_as_second_connection(self):
        rows = self.login_result_vector()
        rows[1]['status'] = 'LOGIN_REJECTED_SERVER_NOT_READY'
        with self.assertRaisesRegex(ValueError, 'login failed'):
            v.second_login_result(rows, 2, 0)

    def test_missing_v2_result_or_result_before_callback_rejected(self):
        rows = self.login_result_vector()
        with self.assertRaisesRegex(ValueError, 'one v2'):
            v.second_login_result([rows[0], rows[2]], 2, 0)
        with self.assertRaisesRegex(ValueError, 'order differs'):
            v.second_login_result(rows, 2, 1)

    def test_injected_callback_is_not_a_native_result(self):
        rows = self.login_result_vector()
        rows[1]['callback_injected'] = True
        with self.assertRaisesRegex(ValueError, 'scope/order'):
            v.second_login_result(rows, 2, 0)

    def test_historical_v1_has_no_fail_fast_marker(self):
        self.assertEqual(v.second_login_result([], 1, 0)['status'], 'PASS')
        with self.assertRaisesRegex(ValueError, 'historical v1'):
            v.second_login_result(self.login_result_vector(), 1, 0)


class ActualTwoSessionScopeControls(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.install = ROOT / 'local/evidence/20261005-p02-inprocess-relogin/relogin02-prepare'
        if not (cls.install / 'native-outcome.json').is_file():
            raise unittest.SkipTest('Closed actual two-session corpus absent; NOT_RUN')
        cls.plan = v.crew.read_json(cls.install / 'install-plan.json', 1024 * 1024)
        cls.outcome = v.crew.read_json(cls.install / 'native-outcome.json')
        local_root = v.config()[1]['local_artifacts_root']
        cls.rows, _ = v.entry.runtime_rows(cls.install, cls.plan, cls.outcome, local_root)
        exported, proof = v.crew.export_evidence(ROOT / 'local/evidence/20261005-p02-ms1-crew/native-ms1-crew-export01.json', local_root)
        cls.expected, _ = v.crew.crew_fixture(ROOT / 'local/server/fixtures/c5326cc1-8524-479c-8bba-72e973489c22/r3-catalog3', exported, proof, local_root)
        cls.transition = v.runtime_transition(cls.rows, cls.plan, cls.outcome)

    def test_actual_middle_disconnected_empty_cache_is_outside_live_account_window(self):
        empty = [r for r in self.rows if r['event'] == 'native_hangar' and r.get('items_cache_synced') is True
                 and r.get('native_connected') is False and r.get('resources', {}).get('credits') == 0]
        self.assertEqual(len(empty), 1)
        self.assertEqual(empty[0]['views']['main']['class_name'], 'LoginView')
        for leg in (1, 2):
            self.assertEqual(v.active_hangar_window(self.rows, leg, self.transition, self.expected)['status'], 'PASS')

    def test_connected_account_balance_change_still_rejected(self):
        for leg in (1, 2):
            rows = copy.deepcopy(self.rows)
            begin = self.transition['native_connected_lines'][leg - 1] - 1
            end = self.transition['logoff_lines'][0] - 1 if leg == 1 else v.only(rows, 'fini_enter')[0]
            sample = next(r for r in rows[begin:end] if r['event'] == 'native_hangar' and r.get('items_cache_synced') is True)
            sample['resources']['credits'] -= 1
            with self.subTest(leg=leg), self.assertRaisesRegex(ValueError, 'resources/statistics changed'):
                v.active_hangar_window(rows, leg, self.transition, self.expected)

    def test_no_implicit_window_without_actual_middle_transition(self):
        with self.assertRaisesRegex(ValueError, 'proved connection lifecycle'):
            v.active_hangar_window(self.rows, 1, {'status': 'FAIL'}, self.expected)

    def test_wrong_identity_in_second_actual_account_is_rejected(self):
        proof_path = ROOT / 'local/evidence/20261005-p02-inprocess-relogin/wire/verify-relogin02-02/inprocess-relogin-verification.json'
        if not proof_path.is_file():
            self.skipTest('Closed independently decoded second wire session absent; NOT_RUN')
        report = v.crew.read_json(proof_path, 32 * 1024 * 1024)
        wire = report['process']['sessions'][1]['checks']['wire']
        split = self.transition['second_submit_line'] - 1
        rows = copy.deepcopy(self.rows[split:])
        player = next(r for r in rows if r['event'] == 'native_player' and r.get('database_id') is not None)
        player['database_id'] += 1
        with self.assertRaisesRegex(ValueError, 'native Account identity'):
            v.crew.native_account(rows, wire, self.expected)

    def test_second_scenario_identity_cannot_reuse_wrong_database_id(self):
        state = next(r['state'] for r in self.rows if r['event'] == 'relogin_scenario_state' and r.get('session_index') == 2)
        with self.assertRaisesRegex(ValueError, 'identity/resources/statistics'):
            v.context({**state, 'database_id': self.expected['native_id'] + 1}, self.expected)

    def test_v2_bundle_cannot_be_downgraded_to_v1_by_changing_trace_markers(self):
        rows = [copy.deepcopy(r) for r in self.rows if r['event'] != 'relogin_scenario_login_result']
        for row in rows:
            if row['event'].startswith('relogin_scenario_'):
                row['version'] = 1
        with self.assertRaisesRegex(ValueError, 'version differs from its compiled source'):
            v.runtime_transition(rows, self.plan, self.outcome)

    def test_unknown_scenario_source_is_not_authenticated_by_self_reported_version(self):
        plan = copy.deepcopy(self.plan)
        next(r for r in plan['sources'] if r['path'] == 'client_patch/hangar_relogin_scenario.py')['sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'compiled source'):
            v.runtime_transition(self.rows, plan, self.outcome)

    def test_logged_on_moved_after_second_account_constructor_is_rejected(self):
        rows = copy.deepcopy(self.rows)
        index = self.transition['native_connected_lines'][1] - 1
        callback = rows.pop(index)
        account_return = next(i for i, r in enumerate(rows) if i > index and r['event'] == 'native_account_call'
                              and r.get('method') == '__init__' and r.get('source_line') == 47 and r.get('phase') == 'return')
        callback['elapsed_seconds'] = (rows[account_return]['elapsed_seconds'] + rows[account_return + 1]['elapsed_seconds']) / 2
        rows.insert(account_return + 1, callback)
        with self.assertRaisesRegex(ValueError, 'logged-on callback must precede'):
            v.runtime_transition(rows, self.plan, self.outcome)

    def test_reusing_first_repository_events_cannot_supply_a_new_second_constructor(self):
        rows = copy.deepcopy(self.rows)
        split = self.transition['second_submit_line'] - 1
        rows = [r for i, r in enumerate(rows) if not (i > split and r['event'] == 'native_account_call'
                and r.get('method') == '__init__' and r.get('source_line') == 1640)]
        with self.assertRaisesRegex(ValueError, 'two fresh original Account/repository'):
            v.runtime_transition(rows, self.plan, self.outcome)


class BackendBuildProofControls(unittest.TestCase):
    """Mutate saved proof in memory only; never run builds or change a service."""
    @classmethod
    def setUpClass(cls):
        cls.directory = v.DEFAULT_BUILD
        install = ROOT / 'local/evidence/20261005-p02-inprocess-relogin/relogin02-prepare'
        if not (install / 'native-outcome.json').is_file() or not (cls.directory / 'after.json').is_file():
            raise unittest.SkipTest('Closed actual build/run proof absent; NOT_RUN')
        cls.outcome = v.crew.read_json(install / 'native-outcome.json')
        cls.local_root = v.config()[1]['local_artifacts_root']
        names = ('before.json', 'after.json', 'build-direct01.command.json', 'start.command.json',
                 'build-direct01.stdout.log', 'build-direct01.stderr.log', 'start.stdout.log', 'start.stderr.log',
                 'stop.stdout.log', 'shell-build-failure.json', 'gateway-before.exe')
        cls.saved = {name: v.local_file(cls.directory, name, 64 * 1024 * 1024) for name in names}

    def proof(self, changes=None, outcome=None):
        data = dict(self.saved)
        data.update(changes or {})
        with patch.object(v, 'local_file', side_effect=lambda directory, name, maximum: data[name]):
            return v.backend_build(self.directory, outcome or self.outcome, self.local_root)

    def changed_json(self, name, change):
        value = v.entry.json_data(self.saved[name])
        change(value)
        return {name: json.dumps(value).encode('utf8')}

    def test_actual_guarded_build_binds_this_native_run_without_live_service(self):
        proof = self.proof()
        self.assertEqual(proof['status'], 'PASS')
        self.assertEqual(proof['executable_sha256'], v.GATEWAY_EXE_SHA)
        self.assertEqual(proof['gateway_run'], self.outcome['gateway_run'])
        self.assertGreater(proof['client_start_after_startup_seconds'], 0)
        self.assertFalse(proof['current_service_state_required'])

    def test_current_source_pin_alone_does_not_accept_another_gateway_run(self):
        outcome = {**self.outcome, 'gateway_run': str(Path(self.outcome['gateway_run']).parent / 'another-run')}
        with self.assertRaisesRegex(ValueError, 'another built gateway run'):
            self.proof(outcome=outcome)

    def test_native_capture_must_also_belong_to_the_built_run(self):
        with self.assertRaisesRegex(ValueError, 'another built gateway run'):
            self.proof(outcome={**self.outcome, 'wire_source': str(self.directory / 'wire')})

    def test_source_hash_substitution_is_rejected(self):
        changes = self.changed_json('after.json', lambda d: d.update(source_sha256='0' * 64))
        with self.assertRaisesRegex(ValueError, 'executable chain differs'):
            self.proof(changes)

    def test_unchanged_old_binary_is_not_a_successful_build(self):
        changes = self.changed_json('after.json', lambda d: d.update(executable_sha256=v.PREVIOUS_GATEWAY_EXE_SHA))
        with self.assertRaisesRegex(ValueError, 'executable chain differs'):
            self.proof(changes)

    def test_direct_build_failure_cannot_be_replaced_with_prior_shell_exit0(self):
        changes = self.changed_json('build-direct01.command.json', lambda d: d.update(exit_code=1))
        with self.assertRaisesRegex(ValueError, 'direct offline build'):
            self.proof(changes)
        changes = self.changed_json('build-direct01.command.json', lambda d: d['argv'].remove('--locked'))
        with self.assertRaisesRegex(ValueError, 'direct offline build'):
            self.proof(changes)

    def test_started_executable_hash_is_bound_separately_from_build_result(self):
        state = v.entry.json_data(self.saved['after.json'])['state']
        next(p for p in state['processes'] if p['role'] == 'gateway')['executable_sha256'] = '0' * 64
        changes = self.changed_json('after.json', lambda d: d.update(state=state))
        changes['start.stdout.log'] = json.dumps(state).encode('utf8')
        with self.assertRaisesRegex(ValueError, 'started gateway executable identity'):
            self.proof(changes)

    def test_client_cannot_predate_recorded_gateway_startup(self):
        with self.assertRaisesRegex(ValueError, 'predates this gateway'):
            self.proof(outcome={**self.outcome, 'started_utc': '2026-10-04T23:40:00+00:00'})

    def test_naive_utc_cannot_hide_run_order(self):
        with self.assertRaisesRegex(ValueError, 'timezone-aware'):
            self.proof(outcome={**self.outcome, 'started_utc': '2026-10-04T23:44:36'})

    def test_old_binary_backup_hash_is_required(self):
        with self.assertRaisesRegex(ValueError, 'executable chain differs'):
            self.proof({'gateway-before.exe': b'unit-substituted-binary'})

    def test_guarded_builder_source_cannot_be_replaced(self):
        with patch.object(v, 'read_limited', return_value=b'unit-helper-without-source-guards'):
            with self.assertRaisesRegex(ValueError, 'rebuild helper source changed'):
                self.proof()

    def test_start_command_must_enable_this_native_capture(self):
        changes = self.changed_json('start.command.json', lambda d: d['argv'].remove('--capture'))
        with self.assertRaisesRegex(ValueError, 'captured gateway startup'):
            self.proof(changes)

    def test_malformed_build_proof_is_an_explicit_failure(self):
        for name in ('before.json', 'after.json', 'build-direct01.command.json', 'start.stdout.log'):
            with self.subTest(file=name), self.assertRaisesRegex(ValueError, 'JSON object required'):
                self.proof({name: b'[]'})
        state = v.entry.json_data(self.saved['after.json'])['state']
        state['processes'] = [None, None]
        changes = self.changed_json('after.json', lambda d: d.update(state=state))
        changes['start.stdout.log'] = json.dumps(state).encode('utf8')
        with self.assertRaisesRegex(ValueError, 'process set differs'):
            self.proof(changes)


class RejectedActualInprocessRun(unittest.TestCase):
    """Preserve the actual first regression failure, rather than relaxing gates."""
    @classmethod
    def setUpClass(cls):
        cls.install = ROOT / 'local/evidence/20261005-p02-inprocess-relogin/relogin01-prepare'
        if not (cls.install / 'native-outcome.json').is_file():
            raise unittest.SkipTest('Closed native in-process negative absent; NOT_RUN')
        cls.plan = v.crew.read_json(cls.install / 'install-plan.json', 1024 * 1024)
        cls.outcome = v.crew.read_json(cls.install / 'native-outcome.json')
        local_root = v.config()[1]['local_artifacts_root']
        cls.rows, _ = v.entry.runtime_rows(cls.install, cls.plan, cls.outcome, local_root)
        exported, proof = v.crew.export_evidence(ROOT / 'local/evidence/20261005-p02-ms1-crew/native-ms1-crew-export01.json', local_root)
        cls.expected, _ = v.crew.crew_fixture(ROOT / 'local/server/fixtures/c5326cc1-8524-479c-8bba-72e973489c22/r3-catalog3', exported, proof, local_root)

    def test_actual_twelve_modules_hash_chain(self):
        self.assertEqual(v.compiled_sources(self.install, self.plan, self.outcome)['status'], 'PASS')

    def test_failed_scenario_does_not_turn_orderly_exit_into_acceptance(self):
        result = v.process_runtime(self.install, self.plan, self.outcome, self.rows)
        self.assertEqual(result['checks']['single_engine_cleanup']['status'], 'PASS')
        self.assertEqual(result['checks']['process_restore']['status'], 'PASS')
        self.assertEqual(result['checks']['native_errors']['status'], 'FAIL')
        self.assertEqual(result['status'], 'FAIL')

    def test_actual_rejected_second_submit_cannot_count_as_logged_on(self):
        with self.assertRaisesRegex(ValueError, 'logged-on callback'):
            v.runtime_transition(self.rows, self.plan, self.outcome)

    def test_fabricated_success_status_still_lacks_second_native_account(self):
        rows = copy.deepcopy(self.rows)
        rejected = [r for r in rows if r['event'] == 'connection_callback' and r.get('status') == 'LOGIN_REJECTED_SERVER_NOT_READY']
        self.assertEqual(len(rejected), 1)
        rejected[0].update(status='LOGGED_ON', native_connected=True)
        with self.assertRaisesRegex(ValueError, 'two fresh original Account/repository'):
            v.runtime_transition(rows, self.plan, self.outcome)

    def test_actual_final_empty_repository_return35_is_not_middle_cleanup(self):
        begin = v.action_pair(self.rows, 'logoff')[0][0]
        end = v.only(self.rows, 'relogin_scenario_disconnected')[0]
        final = [r for r in self.rows[end:] if r['event'] == 'native_logoff_call' and r.get('method') == '_delAccountRepository'
                 and r.get('phase') == 'return']
        self.assertEqual([r['offset'] for r in final], [35])
        proof = v.middle_repository_reset(self.rows, begin, end)
        self.assertEqual(proof['status'], 'PASS')
        self.assertEqual(proof['return_offset'], 71)

    def test_empty_repository_noop_does_not_replace_actual_middle_cleanup(self):
        rows = copy.deepcopy(self.rows)
        begin = v.action_pair(rows, 'logoff')[0][0]
        end = v.only(rows, 'relogin_scenario_disconnected')[0]
        for row in rows[begin:end]:
            if row['event'] == 'native_logoff_call' and row.get('method') == '_delAccountRepository' and row.get('phase') == 'return':
                row['offset'] = 35
        with self.assertRaisesRegex(ValueError, 'normal return'):
            v.middle_repository_reset(rows, begin, end)

    def test_actual_one_server_allocation_cannot_count_as_two(self):
        with self.assertRaisesRegex(ValueError, 'two complete server sessions'):
            v.backend_ranges(self.install, self.outcome, self.expected)

    def test_first_crew_snapshot_does_not_prove_a_second_account(self):
        with self.assertRaisesRegex(ValueError, 'bounded before/after'):
            v.limits.crew_preservation(self.rows, self.expected)

    def test_actual_closed_negative_capture_stays_complete(self):
        rows, raw, report = v.read_capture(self.install, self.outcome)
        self.assertEqual(len(rows), 95)
        self.assertEqual(sum(map(len, raw)), 5182)
        self.assertEqual(report['status'], 'PASS')


if __name__ == '__main__':
    unittest.main(verbosity=2)
