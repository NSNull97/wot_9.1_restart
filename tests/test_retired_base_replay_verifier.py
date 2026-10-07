"""Offline partition controls; unit vectors are never native replay evidence."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import verify_retired_base_replay as v


class ExhaustivePacketPartition(unittest.TestCase):
    def setUp(self):
        self.rows, self.packets = [], []
        for n in range(8):
            raw = bytes([n + 1]) * (n + 2)
            index = n + 10
            self.rows.append({'event': 'packet', 'index': index,
                              'file': 'packet-%06d-base_client_to_server.bin' % index,
                              'direction': 'base_client_to_server', 'channel': 'base', 'peer': '127.0.0.1:32100',
                              'bytes': len(raw), 'sha256': v.digest(raw), 'elapsed_seconds': 0.5 * n})
            self.packets.append(raw)
        self.removed = [11, 13, 14]

    def test_every_unit_packet_is_counted_and_kept_payloads_unchanged(self):
        rows, packets, proof = v.partition_packets(self.rows, self.packets, self.removed)
        self.assertEqual(proof['status'], 'PASS')
        self.assertEqual([r['index'] for r in rows], [10, 11, 12, 13, 14])
        self.assertEqual([r['original_index'] for r in proof['mapping']], list(range(10, 18)))
        self.assertEqual([r['classification'] for r in proof['mapping']].count('replay'), 3)
        wanted = [i for i, r in enumerate(self.rows) if r['index'] not in self.removed]
        self.assertEqual(packets, [self.packets[i] for i in wanted])
        for derived, original in zip(rows, [self.rows[i] for i in wanted]):
            for key in set(original) - {'index', 'file'}:
                self.assertEqual(derived[key], original[key])

    def test_duplicate_exclusion_cannot_hide_missing_third_ingress(self):
        with self.assertRaisesRegex(ValueError, 'three distinct'):
            v.partition_packets(self.rows, self.packets, [11, 11, 13])

    def test_fourth_packet_cannot_be_silently_filtered(self):
        with self.assertRaisesRegex(ValueError, 'three distinct'):
            v.partition_packets(self.rows, self.packets, [11, 13, 14, 15])

    def test_unknown_excluded_index_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'unknown exclusion'):
            v.partition_packets(self.rows, self.packets, [11, 13, 18])

    def test_original_index_gap_is_rejected(self):
        rows = copy.deepcopy(self.rows)
        rows[6]['index'] += 1
        with self.assertRaisesRegex(ValueError, 'index gap'):
            v.partition_packets(rows, self.packets, self.removed)

    def test_changed_raw_payload_is_rejected_before_copy(self):
        packets = list(self.packets)
        packets[3] += b'x'
        with self.assertRaisesRegex(ValueError, 'packet changed'):
            v.partition_packets(self.rows, packets, self.removed)

    def test_equal_logout_bytes_still_have_three_distinct_capture_identities(self):
        rows, packets = copy.deepcopy(self.rows), list(self.packets)
        packets[4] = packets[3]
        rows[4].update(bytes=len(packets[4]), sha256=v.digest(packets[4]))
        _, _, proof = v.partition_packets(rows, packets, self.removed)
        removed = [r for r in proof['mapping'] if r['classification'] == 'replay']
        self.assertEqual(len({r['original_index'] for r in removed}), 3)
        self.assertEqual(removed[1]['sha256'], removed[2]['sha256'])

    def test_boolean_exclusion_is_not_an_index(self):
        with self.assertRaisesRegex(ValueError, 'distinct replay ingress'):
            v.partition_packets(self.rows, self.packets, [True, 13, 14])


class ExhaustiveBackendPartition(unittest.TestCase):
    def vector(self, ending=b'\n'):
        lines = [b'UNIT before', v.REJECTION, b'UNIT middle', v.REJECTION, v.REJECTION, b'UNIT after']
        raw, offsets, pos = b'', [], 1700
        for line in lines:
            if line == v.REJECTION:
                offsets.append(pos)
            raw += line + ending
            pos += len(line) + len(ending)
        return raw, offsets

    def test_every_backend_byte_has_exactly_one_classification(self):
        raw, offsets = self.vector()
        native, proof = v.partition_log(raw, offsets, 1700)
        self.assertEqual(native, b'UNIT before\nUNIT middle\nUNIT after\n')
        self.assertEqual(proof['rejected_line_count'], 3)
        mapping = proof['mapping']
        self.assertEqual(mapping[0]['original_absolute_start'], 1700)
        self.assertEqual(mapping[-1]['original_absolute_end'], 1700 + len(raw))
        self.assertTrue(all(a['original_absolute_end'] == b['original_absolute_start'] for a, b in zip(mapping, mapping[1:])))
        self.assertEqual(sum(r['bytes'] for r in mapping), len(raw))

    def test_crlf_bytes_are_preserved_exactly(self):
        raw, offsets = self.vector(b'\r\n')
        native, _ = v.partition_log(raw, offsets, 1700)
        self.assertEqual(native, b'UNIT before\r\nUNIT middle\r\nUNIT after\r\n')

    def test_partial_line_cannot_be_classified_as_rejection(self):
        raw, offsets = self.vector()
        with self.assertRaisesRegex(ValueError, 'complete bounded'):
            v.partition_log(raw[:-1], offsets, 1700)

    def test_unknown_backend_offset_is_rejected(self):
        raw, offsets = self.vector()
        offsets[0] += 1
        with self.assertRaisesRegex(ValueError, 'only and all'):
            v.partition_log(raw, offsets, 1700)

    def test_fourth_rejection_cannot_be_discarded_or_ignored(self):
        raw, offsets = self.vector()
        with self.assertRaisesRegex(ValueError, 'only and all'):
            v.partition_log(raw + v.REJECTION + b'\n', offsets, 1700)

    def test_other_rejection_is_not_equivalent_to_retired_base_peer(self):
        raw, offsets = self.vector()
        raw = raw.replace(v.REJECTION, b'REJECT reason=other_base_peer', 1)
        with self.assertRaisesRegex(ValueError, 'only and all'):
            v.partition_log(raw, offsets, 1700)

    def test_unrelated_native_error_is_preserved_for_frozen_positive_gate(self):
        raw, offsets = self.vector()
        native, _ = v.partition_log(raw + b'REJECT reason=channel_state\n', offsets, 1700)
        self.assertTrue(native.endswith(b'REJECT reason=channel_state\n'))


class DerivedFileBounds(unittest.TestCase):
    def setUp(self):
        parent = ROOT / 'local/evidence/20261005-p02-retired-base-replay/wire'
        parent.mkdir(parents=True, exist_ok=True)
        self.out = Path(tempfile.mkdtemp(prefix='unit-derived-', dir=parent))

    def test_derivative_cannot_escape_its_owned_output(self):
        with self.assertRaisesRegex(ValueError, 'escaped'):
            v.write_new(self.out, '../escape.bin', b'unit')

    def test_existing_derived_bytes_are_never_overwritten(self):
        path = v.write_new(self.out, 'nested/unit.bin', b'first')
        with self.assertRaises(FileExistsError):
            v.write_new(self.out, 'nested/unit.bin', b'next')
        self.assertEqual(path.read_bytes(), b'first')


class SourceFrameControls(unittest.TestCase):
    def frame(self):
        return {'body_hex': '', 'piggybacks': [], 'cumulative_ack': 1, 'selective_acks': [],
                'flags': '0x448', 'sequence': 4}

    def test_empty_feedback_and_direct_logout_have_distinct_shapes(self):
        self.assertFalse(v.source_frame('feedback', self.frame())['token_present'])
        frame = self.frame()
        frame.update(body_hex='01777777770b00', flags='0x458', sequence=8)
        self.assertTrue(v.source_frame('logout', frame)['token_present'])

    def test_token_prefixed_empty_rpc_is_not_tokenless_feedback(self):
        frame = self.frame()
        frame['body_hex'] = '0177777777'
        with self.assertRaisesRegex(ValueError, 'genuinely tokenless'):
            v.source_frame('feedback', frame)

    def test_hidden_piggyback_cannot_be_replayed_as_feedback(self):
        frame = self.frame()
        frame['piggybacks'] = [self.frame()]
        with self.assertRaisesRegex(ValueError, 'hidden piggybacks'):
            v.source_frame('feedback', frame)

    def test_bodyless_frame_without_feedback_is_rejected(self):
        frame = self.frame()
        frame['cumulative_ack'] = None
        with self.assertRaisesRegex(ValueError, 'genuinely tokenless'):
            v.source_frame('feedback', frame)

    def test_arbitrary_seven_bytes_are_not_a_native_logout(self):
        frame = self.frame()
        frame.update(body_hex='00000000000000', flags='0x458', sequence=8)
        with self.assertRaisesRegex(ValueError, 'authenticated disconnect'):
            v.source_frame('logout', frame)


class OriginalEvidenceControls(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.install = ROOT / 'local/evidence/20261005-p02-account-switch/switch02-prepare'
        if not (cls.install / 'native-outcome.json').is_file():
            raise unittest.SkipTest('Original closed S evidence is unavailable')

    def test_real_s_original_artifacts_pass_without_becoming_replay_evidence(self):
        _, _, _, proof = v.original_artifacts(self.install, v.config()[1]['local_artifacts_root'])
        self.assertEqual(proof['status'], 'PASS')
        self.assertNotIn('replay_proof', proof)
        self.assertEqual(len(proof['checks']['compiled_sources']['modules']), 13)
        self.assertEqual(set(proof['trace']), {'path', 'bytes', 'sha256', 'event_count'})
        self.assertTrue(Path(proof['trace']['path']).is_file())


class PrefixControls(unittest.TestCase):
    def setUp(self):
        self.path = ROOT / 'local/evidence/20261005-p02-retired-base-replay/wire/unit-source'
        self.raw = b'first\nsecond\n'
        self.reference = {'file': str(self.path), 'start_offset': 0, 'end_offset': 6, 'bytes': 6,
                          'sha256': v.digest(b'first\n'), 'lines': 1}

    def test_saved_prefix_does_not_depend_on_later_append(self):
        self.assertEqual(v.prefix_reference(self.reference, self.raw, self.path, 100)[0]['raw'], b'first\n')

    def test_changed_prefix_bytes_fail_even_if_file_length_grew(self):
        with self.assertRaisesRegex(ValueError, 'prefix bytes changed'):
            v.prefix_reference(self.reference, b'other\nsecond\n', self.path, 100)

    def test_foreign_path_is_not_accepted_with_same_hash(self):
        self.reference['file'] += '-foreign'
        with self.assertRaisesRegex(ValueError, 'path or byte bounds'):
            v.prefix_reference(self.reference, self.raw, self.path, 100)

    def test_partial_final_line_cannot_be_checkpoint(self):
        self.reference.update(end_offset=5, bytes=5, sha256=v.digest(b'first'))
        with self.assertRaisesRegex(ValueError, 'newline prefix'):
            v.prefix_reference(self.reference, self.raw, self.path, 100)

    def test_extra_private_hash_field_is_rejected(self):
        self.reference['nonce_sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'reference fields'):
            v.prefix_reference(self.reference, self.raw, self.path, 100)

    def test_line_count_boolean_is_rejected(self):
        self.reference['lines'] = True
        with self.assertRaisesRegex(ValueError, 'line count'):
            v.prefix_reference(self.reference, self.raw, self.path, 100)


class RetentionWindowControls(unittest.TestCase):
    def test_actual_sender_float_lifetime_is_accepted(self):
        self.assertIsNone(v.retained_window(13.0, 0.1, 120.0))

    def test_exact_retention_safety_margin_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'retained-peer lifetime'):
            v.retained_window(117.0, 1.0, 120.0)

    def test_extended_or_nonfinite_lifetime_cannot_pass(self):
        for ttl in (True, 120.1, 121, float('inf'), float('nan'), '120'):
            with self.subTest(ttl=ttl), self.assertRaisesRegex(ValueError, 'retained-peer lifetime'):
                v.retained_window(13.0, 0.1, ttl)


class NativeCheckpointControls(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.install = ROOT / 'local/evidence/20261005-p02-account-switch/switch02-prepare'
        if not (cls.install / 'native-outcome.json').exists():
            raise unittest.SkipTest('Immutable actual S trace unavailable')
        plan = json.loads((cls.install / 'install-plan.json').read_text(encoding='utf8'))
        outcome = json.loads((cls.install / 'native-outcome.json').read_text(encoding='utf8'))
        rows, _ = v.entry.runtime_rows(cls.install, plan, outcome, v.config()[1]['local_artifacts_root'])
        at = next(i for i, r in enumerate(rows) if r['event'] == 'account_switch_state' and r.get('session_index') == 2)
        cls.saved = rows[:at + 1]
        cls.expected = cls.saved[-1]['state']['account']

    def setUp(self):
        self.rows = copy.deepcopy(self.saved)
        state = self.rows[-1]
        hline = max(i + 1 for i, r in enumerate(self.rows) if r['event'] == 'native_hangar')
        self.context = {'session_index': 2, 'ready_line': len(self.rows), 'hangar_line': hline,
                        'stable_seconds': state['stable_seconds'], 'native_elapsed_seconds': state['elapsed_seconds'],
                        'host_seconds_since_ready': 0.1, 'host_seconds_since_hangar': 0.2, 'account': copy.deepcopy(self.expected),
                        'crew_owner': state['state']['crew_owner'], 'hangar_owner': state['state']['hangar_owner']}
        self.reference = {'lines': len(self.rows), 'last_ready_line': len(self.rows)}

    def check(self):
        return v.native_checkpoint(self.context, self.reference, self.rows, self.expected, True)

    def test_actual_secondary_prefix_is_ready_without_any_replay_claim(self):
        self.assertEqual(self.check()['ready_line'], len(self.rows))

    def test_fini_enter_before_send_rejects_even_with_stale_ready(self):
        self.rows.append({'event': 'fini_enter'})
        self.reference['lines'] += 1
        with self.assertRaisesRegex(ValueError, 'fini/error'):
            self.check()

    def test_b_logout_before_send_rejects(self):
        self.rows.append({'event': 'account_switch_action', 'session_index': 2, 'action': 'logoff'})
        self.reference['lines'] += 1
        with self.assertRaisesRegex(ValueError, 'began logout'):
            self.check()

    def test_notready_latest_model_cannot_use_old_ready_marker(self):
        self.rows[self.context['hangar_line'] - 1]['items_cache_synced'] = False
        with self.assertRaisesRegex(ValueError, 'not ready'):
            self.check()

    def test_rejected_login_cannot_be_substituted_for_secondary_auth(self):
        callbacks = [r for r in self.rows if r['event'] == 'connection_callback' and r.get('stage') == 1]
        callbacks[-1]['status'] = 'LOGIN_REJECTED_SERVER_NOT_READY'
        with self.assertRaisesRegex(ValueError, 'LOGGED_ON'):
            self.check()

    def test_secondary_credit_change_is_rejected(self):
        self.rows[self.context['hangar_line'] - 1]['resources']['credits'] += 1
        with self.assertRaisesRegex(ValueError, 'resources changed'):
            self.check()

    def test_copied_primary_identity_is_rejected(self):
        self.rows[-1]['state']['account']['database_id'] = 1
        with self.assertRaisesRegex(ValueError, 'account changed'):
            self.check()

    def test_stale_observation_is_rejected(self):
        self.context['host_seconds_since_ready'] = 2.001
        with self.assertRaisesRegex(ValueError, 'stale native'):
            self.check()


class SendBracketControls(unittest.TestCase):
    def setUp(self):
        self.raw = b'UNIT_CIPHERTEXT_ONLY'
        self.candidate = {'index': 30, 'file': 'source-unit.bin', 'peer': '127.0.0.1:32001', 'bytes': len(self.raw),
                          'sha256': v.digest(self.raw), 'elapsed_seconds': 5.0, 'kind': 'tokenless_feedback'}
        self.row = {'event': 'packet', 'index': 120, 'file': 'ingress-unit.bin', 'direction': 'base_client_to_server',
                    'channel': 'base', 'peer': self.candidate['peer'], 'bytes': len(self.raw), 'sha256': v.digest(self.raw),
                    'elapsed_seconds': 12.0}
        self.reject = {'line': 4, 'start_offset': 100, 'end_offset': 100 + len(v.REJECTION) + 1, 'raw': v.REJECTION + b'\n'}
        self.before = {'send_index': 1, 'candidate': copy.deepcopy(self.candidate), 'source': ['127.0.0.1', 32001],
                       'destination': ['127.0.0.1', 20016], 'checkpoint': {'host_monotonic': 20.0,
                        'utc': '2026-10-05T01:00:00+00:00', 'sources': {'capture': {'last_index': 119}, 'gateway': {'end_offset': 100}}}}
        self.sent = {'send_index': 1, 'candidate': copy.deepcopy(self.candidate), 'bytes_returned': len(self.raw),
                     'host_monotonic': 20.1, 'utc': '2026-10-05T01:00:01+00:00'}
        self.after = {'send_index': 1, 'status': 'PASS', 'ingress': {k: self.row[k] for k in
                      ('index', 'file', 'peer', 'bytes', 'sha256', 'elapsed_seconds')},
                      'rejection': {k: self.reject[k] for k in ('line', 'start_offset', 'end_offset')},
                      'checkpoint': {'host_monotonic': 20.2, 'utc': '2026-10-05T01:00:02+00:00',
                        'sources': {'capture': {'last_index': 120}, 'gateway': {'end_offset': self.reject['end_offset']}}}}
        self.after['rejection']['text'] = v.REJECTION.decode()
        self.rows, self.packets, self.lines = [self.row], [self.raw], [self.reject]

    def check(self):
        return v.send_bracket(self.before, self.sent, self.after, self.candidate, self.rows, self.packets, self.lines, [0, 1], 5.0)

    def test_complete_unit_bracket_matches_only_one_ingress_and_reject(self):
        self.assertEqual(self.check()['ingress']['index'], 120)

    def test_wrong_source_peer_is_rejected(self):
        self.before['source'][1] += 1
        with self.assertRaisesRegex(ValueError, 'old loopback'):
            self.check()

    def test_altered_ciphertext_is_rejected(self):
        self.packets[0] = b'ALTERED_UNIT_BYTES'
        with self.assertRaisesRegex(ValueError, 'ciphertext'):
            self.check()

    def test_two_old_peer_ingresses_in_one_bracket_are_ambiguous(self):
        self.rows *= 2
        self.packets *= 2
        with self.assertRaisesRegex(ValueError, 'exactly one old-peer'):
            self.check()

    def test_ingress_outside_before_after_prefix_is_rejected(self):
        self.before['checkpoint']['sources']['capture']['last_index'] = 120
        with self.assertRaisesRegex(ValueError, 'exactly one old-peer'):
            self.check()

    def test_replayed_ciphertext_after_ttl_is_not_accepted(self):
        self.row['elapsed_seconds'] = 125.0
        self.after['ingress']['elapsed_seconds'] = 125.0
        with self.assertRaisesRegex(ValueError, 'TTL'):
            self.check()

    def test_wrong_rejection_reason_is_not_counted(self):
        self.reject['raw'] = b'REJECT reason=channel_state\n'
        with self.assertRaisesRegex(ValueError, 'exactly one exact'):
            self.check()

    def test_declared_rejection_offset_cannot_select_other_line(self):
        self.after['rejection']['start_offset'] += 1
        with self.assertRaisesRegex(ValueError, 'rejection differs'):
            self.check()

    def test_partial_udp_write_cannot_be_pass(self):
        self.sent['bytes_returned'] -= 1
        with self.assertRaisesRegex(ValueError, 'partial replay'):
            self.check()

    def test_sent_timestamp_must_be_inside_bracket(self):
        self.sent['host_monotonic'] = 19.9
        with self.assertRaisesRegex(ValueError, 'before/after bracket'):
            self.check()

    def test_oversize_replay_is_rejected_even_before_hash_correlation(self):
        self.candidate['bytes'] = 1025
        self.before['candidate']['bytes'] = self.sent['candidate']['bytes'] = 1025
        with self.assertRaisesRegex(ValueError, '1024-byte'):
            self.check()


class FrozenSenderLedgerControls(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = ROOT / 'local/evidence/20261005-p02-retired-base-replay/probe01'
        if not (cls.source / 'result.json').is_file():
            raise unittest.SkipTest('Closed actual sender ledger unavailable')
        cls.ledger, cls.proof = v.ledger_files(cls.source)

    def copied(self, name, mutate):
        parent = ROOT / 'local/evidence/20261005-p02-retired-base-replay/wire'
        folder = Path(tempfile.mkdtemp(prefix='unit-ledger-', dir=parent))
        rows = copy.deepcopy(self.ledger)
        mutate(rows[name])
        for filename, row in rows.items():
            (folder / filename).write_text(json.dumps(row), encoding='utf8')
        return folder

    def test_actual_sender_ledger_schema_is_not_native_acceptance(self):
        self.assertEqual(self.proof['status'], 'PASS')
        self.assertEqual(self.ledger['result.json']['native_card_status'], 'NOT_RUN')

    def test_extra_private_value_in_result_is_rejected(self):
        folder = self.copied('result.json', lambda row: row.update(password='UNIT_NONSECRET_SENTINEL'))
        with self.assertRaisesRegex(ValueError, 'ledger fields'):
            v.ledger_files(folder)

    def test_extra_private_digest_in_armed_is_rejected(self):
        folder = self.copied('armed.json', lambda row: row.update(nonce_sha256='0' * 64))
        with self.assertRaisesRegex(ValueError, 'ledger fields'):
            v.ledger_files(folder)

    def test_extra_private_value_in_sent_is_rejected(self):
        folder = self.copied('send-02-sent.json', lambda row: row.update(password='UNIT_NONSECRET_SENTINEL'))
        with self.assertRaisesRegex(ValueError, 'ledger fields'):
            v.ledger_files(folder)

    def test_four_syscall_attempts_cannot_claim_three_sends(self):
        folder = self.copied('result.json', lambda row: row.update(attempted_sends=4))
        with self.assertRaisesRegex(ValueError, 'exactly three'):
            v.ledger_files(folder)

    def test_attempt_counter_bool_cannot_claim_success(self):
        folder = self.copied('result.json', lambda row: row.update(attempted_sends=True))
        with self.assertRaisesRegex(ValueError, 'exactly three'):
            v.ledger_files(folder)

    def test_wrong_sender_version_hash_is_rejected(self):
        folder = self.copied('result.json', lambda row: row.update(helper_sha256='0' * 64))
        with self.assertRaisesRegex(ValueError, 'frozen reviewed sender'):
            v.ledger_files(folder)

    def test_fourth_send_record_cannot_be_ignored_by_fixed_name_reader(self):
        folder = self.copied('result.json', lambda row: None)
        (folder / 'send-04-sent.json').write_text('{}', encoding='utf8')
        with self.assertRaisesRegex(ValueError, 'extra replay send'):
            v.ledger_files(folder)


if __name__ == '__main__':
    unittest.main(verbosity=2)
