"""Bounded evidence/parser controls. Synthetic vectors never count as native runs."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import verify_account_switch as v


class ThreeAccountParserControls(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        parent = ROOT / 'local/evidence/20261005-p02-account-switch/wire'
        parent.mkdir(parents=True, exist_ok=True)
        cls.scratch = Path(tempfile.mkdtemp(prefix='parser-controls-', dir=parent))
        (cls.scratch / 'unit-only.json').write_text(json.dumps({'native_acceptance': False,
            'scope': 'Synthetic byte/metadata controls only; no client or server is launched.'}), encoding='utf8')

    def setUp(self):
        self.accounts = [dict(account_id='unit-primary', native_id=1, name='Primary', raw={k: bytes(n) for k, n in
                         [('state.bin', 12), ('shop.bin', 8), ('dossier.bin', 4)]}),
                         dict(account_id='unit-secondary', native_id=2, name='Secondary', raw={k: bytes(n) for k, n in
                         [('state.bin', 7), ('shop.bin', 6), ('dossier.bin', 3)]})]

    def backend(self, change=None):
        lines = []
        for i, account in enumerate(v.account_sequence(self.accounts), 1):
            lines += ['AUTH_PENDING request_id=%d allocated=0' % (100 + i),
                      'SESSION_PENDING id=%d account=%s native_database_id=%d name=%s allocated=1 source=website_users fixture_sizes=[%s]' %
                      (i, account['account_id'], account['native_id'], account['name'], ', '.join(str(len(account['raw'][k]))
                          for k in ('state.bin', 'shop.bin', 'dossier.bin'))),
                      'SESSION_ACTIVE id=%d account=%s active=1' % (i, account['account_id']),
                      'SESSION_CLOSED id=%d reason=client_disconnect active=0 pending=0 retired_pending=0' % i]
        if change:
            change(lines)
        raw = ('\n'.join(lines) + '\n').encode('utf8')
        outcome = {'gateway_log_span': {'file': 'gateway-span.log', 'sha256': v.digest(raw), 'start_offset': 0, 'end_offset': len(raw)}}
        with patch.object(v, 'local_file', return_value=raw):
            return v.backend_ranges(self.scratch, outcome, self.accounts)

    def test_three_format_valid_workers_and_retirements_are_not_native_acceptance(self):
        raw, bounds, proof = self.backend()
        self.assertEqual(proof['status'], 'PASS')
        self.assertEqual([s['account_id'] for s in proof['sessions']], ['unit-primary', 'unit-secondary', 'unit-primary'])
        self.assertEqual(len(bounds), 4)
        self.assertEqual(bounds[-1], len(raw))
        self.assertFalse(proof['pending_literal_is_auth_worker_evidence'])

    def test_duplicate_domain_or_native_identity_is_rejected(self):
        for key in ('account_id', 'native_id', 'name'):
            accounts = copy.deepcopy(self.accounts)
            accounts[1][key] = accounts[0][key]
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, 'identity must differ'):
                v.account_sequence(accounts)

    def test_secondary_cannot_receive_primary_allocation(self):
        def change(lines):
            lines[5] = lines[1].replace('id=1 ', 'id=2 ')
        with self.assertRaisesRegex(ValueError, 'identity/fixture isolation'):
            self.backend(change)

    def test_primary_return_cannot_remain_secondary(self):
        def change(lines):
            lines[9] = lines[5].replace('id=2 ', 'id=3 ')
        with self.assertRaisesRegex(ValueError, 'identity/fixture isolation'):
            self.backend(change)

    def test_same_size_does_not_replace_uuid_identity(self):
        def change(lines):
            lines[5] = lines[5].replace('unit-secondary', 'unit-foreign')
        with self.assertRaisesRegex(ValueError, 'identity/fixture isolation'):
            self.backend(change)

    def test_prior_retirement_must_precede_next_allocation(self):
        def change(lines):
            line = lines.pop(3)
            lines.insert(6, line)
        with self.assertRaisesRegex(ValueError, 'before prior retirement'):
            self.backend(change)

    def test_reused_server_session_id_is_rejected(self):
        def change(lines):
            lines[:] = [s.replace('id=3 ', 'id=1 ') for s in lines]
        with self.assertRaisesRegex(ValueError, 'session identity reused'):
            self.backend(change)

    def test_pending_duplicate_does_not_prove_fresh_authentication(self):
        def change(lines):
            lines[4] = lines[4].replace('AUTH_PENDING ', 'AUTH_PENDING_DUPLICATE ')
        with self.assertRaisesRegex(ValueError, 'fresh credential worker'):
            self.backend(change)

    def test_two_successful_sessions_do_not_prove_three(self):
        with self.assertRaisesRegex(ValueError, 'exactly three'):
            self.backend(lambda lines: lines.__delitem__(slice(8, None)))

    def test_unexpected_fourth_session_rejected(self):
        def change(lines):
            lines.extend(lines[-4:])
        with self.assertRaisesRegex(ValueError, 'extra backend allocation'):
            self.backend(change)

    def packet_vector(self):
        packets = [bytes([n]) * (n + 1) for n in range(6)]
        rows = [{'index': n + 20, 'file': 'unit-%d.bin' % n, 'bytes': len(raw), 'sha256': v.digest(raw)}
                for n, raw in enumerate(packets)]
        proof = {'status': 'PASS', 'file': 'synthetic-parser-only.json', 'sha256': '0' * 64,
                 'first_index': 20, 'packet_count': 6, 'wire_bytes': sum(map(len, packets))}
        outcome = {'gateway_run': 'unit-only', 'gateway_log_span': {'start_offset': 7}}
        return rows, packets, proof, outcome

    def derived(self, rows=None, packets=None, bounds=None, backend_bounds=None):
        original_rows, original_packets, proof, outcome = self.packet_vector()
        out = Path(tempfile.mkdtemp(prefix='derived-unit-', dir=self.scratch))
        return v.derive_segments(out, rows or original_rows, packets or original_packets,
                                  bounds or [0, 2, 4, 6], proof, b'abcdef', backend_bounds or [0, 2, 4, 6], outcome)

    def test_three_derived_segments_preserve_every_original_test_byte_once(self):
        derived, proof = self.derived()
        self.assertTrue(proof['all_source_packets_used_once'])
        self.assertTrue(proof['all_source_backend_bytes_used_once'])
        self.assertFalse(proof['native_packet_generation'])
        original = self.packet_vector()[1]
        actual = []
        for path, _ in derived:
            manifest = json.loads((path / 'wire/capture.json').read_text(encoding='utf8'))
            self.assertFalse(manifest['derivation']['native_capture'])
            actual.extend((path / 'wire' / row['file']).read_bytes() for row in manifest['packets'])
        self.assertEqual(actual, original)

    def test_empty_or_overlapping_segment_bounds_are_rejected(self):
        for bounds in ([0, 2, 2, 6], [0, 4, 2, 6], [1, 2, 4, 6], [0, 2, 4, 5]):
            with self.subTest(bounds=bounds), self.assertRaisesRegex(ValueError, 'contiguous packet'):
                self.derived(bounds=bounds)

    def test_packet_index_gap_cannot_be_relabelled_as_complete(self):
        rows = self.packet_vector()[0]
        rows[3]['index'] += 1
        with self.assertRaisesRegex(ValueError, 'lost/duplicated/reordered'):
            self.derived(rows=rows)

    def test_payload_mutation_after_hash_check_is_rejected(self):
        packets = self.packet_vector()[1]
        packets[2] = b'x' * len(packets[2])
        with self.assertRaisesRegex(ValueError, 'native bytes changed'):
            self.derived(packets=packets)

    def test_backend_gap_or_overlap_is_rejected(self):
        for bounds in ([0, 2, 2, 6], [0, 4, 2, 6], [1, 2, 4, 6], [0, 2, 4, 7]):
            with self.subTest(bounds=bounds), self.assertRaisesRegex(ValueError, 'backend spans'):
                self.derived(backend_bounds=bounds)

    def test_third_worker_must_correlate_to_its_actual_native_reply(self):
        _, _, lifecycle = self.backend()
        wire = {'status': 'PASS', 'login_requests': [{'request': 103}], 'login_replies': [{'request': 103}]}
        self.assertEqual(v.fresh_auth_binding(lifecycle, 3, wire)['status'], 'PASS')
        wire['login_replies'] = [{'request': 102}]
        with self.assertRaisesRegex(ValueError, 'actual native exchange|native exchange'):
            v.fresh_auth_binding(lifecycle, 3, wire)


class SnapshotIsolationControls(unittest.TestCase):
    """Primitive vectors exercise rejection logic; they are not native data."""
    def setUp(self):
        self.secondary = {'database_id': 2, 'name': 'UnitSecondary',
            'resources': {'credits': 100000, 'gold': 0, 'free_xp': 0},
            'statistics': {'battles': 0, 'wins': 0, 'losses': 0, 'draws': 0},
            'account_dossier_sha256': 'a' * 64,
            'vehicles': [{'inventory_id': 1, 'type_compact_descr': 3329, 'compact_descr_sha256': 'b' * 64,
                          'health': 90, 'crew_ids': [None, None]}], 'tankmen': []}
        self.primary = copy.deepcopy(self.secondary)
        self.primary.update(database_id=1, name='UnitPrimary', account_dossier_sha256='c' * 64)
        self.primary['vehicles'].append({'inventory_id': 2, 'type_compact_descr': 7169, 'compact_descr_sha256': 'd' * 64,
                                         'health': 2150, 'crew_ids': [None] * 5})
        self.primary['vehicles'][0]['crew_ids'] = [1, 2]
        self.primary['tankmen'] = [{'inventory_id': n, 'compact_descr_sha256': 'e' * 64,
                                   'vehicle_inventory_id': 1, 'vehicle_slot_index': n - 1} for n in (1, 2)]

    def test_equal_resources_do_not_hide_secondary_foreign_is7(self):
        wrong = copy.deepcopy(self.secondary)
        wrong['vehicles'].append(copy.deepcopy(self.primary['vehicles'][1]))
        self.assertEqual(wrong['resources'], self.primary['resources'])
        with self.assertRaisesRegex(ValueError, 'inventory/crew/dossier identity'):
            v.account_snapshot(wrong, self.secondary)

    def test_secondary_cannot_inherit_primary_tankmen(self):
        wrong = copy.deepcopy(self.secondary)
        wrong['tankmen'] = copy.deepcopy(self.primary['tankmen'])
        wrong['vehicles'][0]['crew_ids'] = [1, 2]
        with self.assertRaisesRegex(ValueError, 'inventory/crew/dossier identity'):
            v.account_snapshot(wrong, self.secondary)

    def test_secondary_own_registration_dossier_cannot_be_replaced(self):
        with self.assertRaisesRegex(ValueError, 'inventory/crew/dossier identity'):
            v.account_snapshot({**self.secondary, 'account_dossier_sha256': self.primary['account_dossier_sha256']}, self.secondary)

    def test_primary_return_requires_is7_and_both_native_crew(self):
        for field in ('vehicles', 'tankmen'):
            wrong = copy.deepcopy(self.primary)
            wrong[field] = copy.deepcopy(self.secondary[field])
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, 'inventory/crew/dossier identity'):
                v.account_snapshot(wrong, self.primary)

    def test_wrong_native_id_or_nickname_rejected(self):
        for field in ('database_id', 'name'):
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, 'inventory/crew/dossier identity'):
                v.account_snapshot({**self.secondary, field: self.primary[field]}, self.secondary)

    def test_exact_empty_secondary_is_distinct_from_restored_primary(self):
        first = v.account_snapshot(self.primary, self.primary)
        second = v.account_snapshot(self.secondary, self.secondary)
        third = v.account_snapshot(copy.deepcopy(self.primary), self.primary)
        self.assertEqual(first, third)
        self.assertNotEqual(first, second)

    def test_boolean_native_id_does_not_equal_integer_identity(self):
        with self.assertRaisesRegex(ValueError, 'inventory/crew/dossier identity'):
            v.account_snapshot({**self.primary, 'database_id': True}, self.primary)

    def test_source_version_is_bound_to_the_compiled_switch_producer(self):
        rows = [{'event': 'account_switch_start', 'version': 1}]
        plan = {'sources': [{'path': 'client_patch/account_switch_scenario.py', 'sha256': v.SCENARIO_SHA}]}
        self.assertEqual(v.scenario_version(rows, plan), 1)
        for mutated_rows, mutated_plan in (([{'event': 'account_switch_start', 'version': 2}], plan),
                                          (rows, {'sources': [{'path': 'client_patch/account_switch_scenario.py', 'sha256': '0' * 64}]})):
            with self.assertRaisesRegex(ValueError, 'version/source identity'):
                v.scenario_version(mutated_rows, mutated_plan)

    def flash_vector(self):
        def event(method, phase, call_id, line, source, offset):
            return {'event': 'native_crew_call', 'method': method, 'phase': phase, 'call_id': call_id,
                    'source_line': line, 'source': source, 'offset': offset, 'owner_id': 9, 'flash_bound': True}
        update = event('updateTankmen', 'call', 1, 42, v.crew.CREW_SOURCES[1][0], -1)
        meta = event('as_tankmenResponseS', 'call', 2, 59, v.crew.CREW_SOURCES[0][0], -1)
        meta.update(roles=[{'roleType': 'commander', 'slot': 0, 'tankmanID': None},
                           {'roleType': 'driver', 'slot': 1, 'tankmanID': None}], tankmen=[])
        return [update, meta, {**meta, 'phase': 'return', 'offset': 30}, {**update, 'phase': 'return', 'offset': 1066}]

    def test_secondary_original_flash_projection_is_empty_not_fake_primary(self):
        self.assertEqual(v.crew_flash(self.flash_vector(), False)['status'], 'PASS')
        wrong = self.flash_vector()
        wrong[1]['tankmen'] = wrong[2]['tankmen'] = [{'tankmanID': 1}]
        with self.assertRaisesRegex(ValueError, 'foreign tankmen'):
            v.crew_flash(wrong, False)

    def test_unbound_meta_fallback_is_not_a_render_success(self):
        wrong = self.flash_vector()
        wrong[2]['offset'] = 34
        with self.assertRaisesRegex(ValueError, 'normal return'):
            v.crew_flash(wrong, False)

    def test_primary_flash_gates_cannot_accept_secondary_empty_roles(self):
        with self.assertRaisesRegex(ValueError, 'two MS1 crew'):
            v.crew_flash(self.flash_vector(), True)

    def cache_vector(self, primary):
        commands = [{'kind': 'sync', 'request': 1, 'command': 100, 'revision': 0, 'persistent_crc': -23},
                    {'kind': 'sync', 'request': 2, 'command': 300, 'revision': 0, 'cached_bytes': 518, 'cached_crc32_signed': -42},
                    {'kind': 'sync', 'request': 3, 'command': 600, 'revision': 1 if primary else 0,
                     'last_change_time': 12345 if primary else 0},
                    {'kind': 'refresh', 'request': 4, 'command': 100, 'revision': 1, 'persistent_crc': -23}]
        session = {'checks': {'wire': {'status': 'PASS', 'commands': commands}, 'cache_backend': {'status': 'PASS'}}}
        expected = {'dossier_cache': {'version': 1, 'last_change_time': 12345, 'vehicle_type_compact_descr': 7169} if primary else None}
        return session, expected

    def test_secondary_dossier_cursor_is_independent_of_primary(self):
        secondary, expected = self.cache_vector(False)
        self.assertEqual(v.cache_snapshot(secondary, expected, False)['dossier_version'], 0)
        secondary['checks']['wire']['commands'][2].update(revision=1, last_change_time=12345)
        with self.assertRaisesRegex(ValueError, 'secondary inherited primary dossier'):
            v.cache_snapshot(secondary, expected, False)

    def test_secondary_advisory_cache_may_be_cold_without_faking_inventory(self):
        secondary, expected = self.cache_vector(False)
        commands = secondary['checks']['wire']['commands']
        commands[0]['persistent_crc'] = commands[3]['persistent_crc'] = 0
        commands[1].update(cached_bytes=0, cached_crc32_signed=0)
        self.assertEqual(v.cache_snapshot(secondary, expected, False)['account_persistent_crc'], 0)

    def test_primary_cache_and_refresh_require_measured_own_descriptor(self):
        primary, expected = self.cache_vector(True)
        self.assertEqual(v.cache_snapshot(primary, expected, True)['account_persistent_crc'], -23)
        primary['checks']['wire']['commands'][3]['persistent_crc'] = -24
        with self.assertRaisesRegex(ValueError, 'own descriptor'):
            v.cache_snapshot(primary, expected, True)


class ConstructorOrderControls(unittest.TestCase):
    def vector(self):
        rows, connected, ends = [], [], []
        for n in range(3):
            connected.append(len(rows))
            rows.append({'event': 'unit_connected_marker'})
            for method, line, phase, offset, call in [('__init__', 47, 'call', -1, n * 10 + 1),
                ('__init__', 1640, 'call', -1, n * 10 + 2), ('__init__', 1640, 'return', 298, n * 10 + 2),
                ('__init__', 47, 'return', 674, n * 10 + 1), ('onBecomePlayer', 210, 'call', -1, n * 10 + 3)]:
                rows.append({'event': 'native_account_call', 'source': 'scripts/client/Account.py', 'method': method,
                             'source_line': line, 'phase': phase, 'offset': offset, 'call_id': call, 'owner_id': 1})
            ends.append(len(rows))
            rows.append({'event': 'unit_original_logoff_or_fini_marker'})
        return rows, connected, ends

    def test_three_fresh_repository_entries_can_reuse_native_object_addresses(self):
        self.assertEqual(v.constructor_order(*self.vector())['status'], 'PASS')

    def test_third_logged_on_must_precede_third_constructor(self):
        rows, connected, ends = self.vector()
        connected[2] += 4
        with self.assertRaisesRegex(ValueError, 'preceded actual LOGGED_ON'):
            v.constructor_order(rows, connected, ends)

    def test_constructor_normal_return_cannot_be_omitted(self):
        rows, connected, ends = self.vector()
        rows[connected[1] + 4]['offset'] = 0
        with self.assertRaisesRegex(ValueError, 'normal return'):
            v.constructor_order(rows, connected, ends)


class CapturedSwitchControls(unittest.TestCase):
    """Read-only regressions over S02; substitutions live only in memory."""
    @classmethod
    def setUpClass(cls):
        cls.install = ROOT / 'local/evidence/20261005-p02-account-switch/switch02-prepare'
        report_path = ROOT / 'local/evidence/20261005-p02-account-switch/wire/verify-switch02-01/account-switch-verification.json'
        if not report_path.is_file():
            raise unittest.SkipTest('Closed native switch02 evidence is not installed')
        raw = report_path.read_bytes()
        if v.digest(raw) != '2b30ca33721edc0fa1322e161d5727884095771568dc4f75ea899f668c05b901':
            raise AssertionError('Frozen native switch02 report differs')
        cls.report = json.loads(raw)
        cls.local_root = v.config()[1]['local_artifacts_root']
        cls.plan = v.entry.json_data((cls.install / 'install-plan.json').read_bytes())
        cls.outcome = v.entry.json_data((cls.install / 'native-outcome.json').read_bytes())
        cls.rows, cls.trace = v.entry.runtime_rows(cls.install, cls.plan, cls.outcome, cls.local_root)
        v.frozen_dependencies()
        import account_switch_expectations
        pair = account_switch_expectations.load_pair(
            ROOT / 'local/server/fixtures/c5326cc1-8524-479c-8bba-72e973489c22/r3-catalog3',
            ROOT / 'local/server/fixtures/271022a3-41e0-406e-b6fa-59930c320442/r1-catalog2',
            ROOT / 'local/evidence/20261005-p02-ms1-crew/native-ms1-crew-export01.json', cls.local_root)
        cls.expected, cls.public = pair['expected'], pair['expected_accounts']
        cls.transition = v.runtime_transition(cls.rows, cls.plan, cls.outcome)

    def scenario(self, rows):
        return v.scenario(rows, self.plan, self.expected, self.public, self.transition, self.local_root)

    def test_actual_three_account_baseline_is_accepted(self):
        self.assertEqual(v.compiled_sources(self.install, self.plan, self.outcome)['status'], 'PASS')
        proof = self.scenario(self.rows)
        self.assertEqual(proof['status'], 'PASS')
        self.assertEqual([len(s['vehicles']) for s in proof['snapshots']], [2, 1, 2])
        self.assertEqual([len(s['tankmen']) for s in proof['snapshots']], [2, 0, 2])
        self.assertEqual(v.visual_review(self.install, self.trace['sha256'], proof)['status'], 'PASS')

    def test_actual_public_runner_metadata_has_no_credential_digest(self):
        control = self.outcome['diagnostic_control']
        self.assertNotIn('sha256', control)
        self.assertFalse(any('password' in key or 'username' in key for key in control))

    def test_actual_public_metadata_rejects_added_secret_values_or_digest(self):
        for key in ('sha256', 'password', 'alternate_password', 'username', 'alternate_username', 'account_switch_expected'):
            outcome = copy.deepcopy(self.outcome)
            outcome['diagnostic_control'][key] = 'UNIT_NONSECRET_SENTINEL'
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, 'exact redacted public control'):
                v.runtime_transition(self.rows, self.plan, outcome)

    def test_actual_public_metadata_rejects_missing_field_or_invalid_types(self):
        for key, value in (('bytes', True), ('bytes', 8193), ('plaintext_recorded', True)):
            outcome = copy.deepcopy(self.outcome)
            outcome['diagnostic_control'][key] = value
            with self.subTest(key=key, value=value), self.assertRaisesRegex(ValueError, 'bounded redacted control'):
                v.runtime_transition(self.rows, self.plan, outcome)
        outcome = copy.deepcopy(self.outcome)
        del outcome['diagnostic_control']['plaintext_recorded']
        with self.assertRaisesRegex(ValueError, 'exact redacted public control'):
            v.runtime_transition(self.rows, self.plan, outcome)

    def test_actual_secondary_cannot_inherit_primary_fleet_or_crew(self):
        for field in ('vehicles', 'tankmen', 'account_dossier_sha256'):
            rows = copy.deepcopy(self.rows)
            snapshot = next(r for r in rows if r['event'] == 'account_switch_snapshot' and r['session_index'] == 2)
            snapshot['snapshot'][field] = copy.deepcopy(self.public[0][field])
            snapshot['fingerprint'] = v.fingerprint(snapshot['snapshot'])
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, 'switched account inventory/crew/dossier'):
                self.scenario(rows)

    def test_actual_primary_return_must_restore_both_tankmen(self):
        rows = copy.deepcopy(self.rows)
        snapshot = next(r for r in rows if r['event'] == 'account_switch_snapshot' and r['session_index'] == 3)
        snapshot['snapshot']['tankmen'] = []
        snapshot['fingerprint'] = v.fingerprint(snapshot['snapshot'])
        with self.assertRaisesRegex(ValueError, 'switched account inventory/crew/dossier'):
            self.scenario(rows)

    def test_actual_source_pin_cannot_be_replaced_by_marker_version(self):
        plan = copy.deepcopy(self.plan)
        source = next(s for s in plan['sources'] if s['path'] == 'client_patch/account_switch_scenario.py')
        source['sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'version/source'):
            v.runtime_transition(self.rows, plan, self.outcome)

    def test_actual_third_connected_callback_cannot_follow_its_constructor(self):
        rows = copy.deepcopy(self.rows)
        at = self.transition['native_connected_lines'][2] - 1
        callback = rows.pop(at)
        after = next(i for i in range(at, len(rows)) if rows[i]['event'] == 'native_account_call'
                     and rows[i].get('method') == '__init__' and rows[i].get('source_line') == 47
                     and rows[i].get('phase') == 'return')
        callback['elapsed_seconds'] = rows[after]['elapsed_seconds']
        rows.insert(after + 1, callback)
        with self.assertRaisesRegex(ValueError, 'preceded actual LOGGED_ON'):
            v.runtime_transition(rows, self.plan, self.outcome)

    def test_actual_middle_login_view_must_not_retain_repository(self):
        rows = copy.deepcopy(self.rows)
        row = next(r for r in rows if r['event'] == 'account_switch_disconnected' and r['session_index'] == 2)
        row['state']['repository_absent'] = False
        with self.assertRaises(ValueError):
            v.runtime_transition(rows, self.plan, self.outcome)

    def test_actual_secondary_flash_cannot_contain_a_primary_tankman(self):
        begin, end = [i - 1 for i in self.transition['subsequent_submit_lines']]
        rows = copy.deepcopy(self.rows[begin:end])
        for row in rows:
            if row['event'] == 'native_crew_call' and row.get('method') == 'as_tankmenResponseS':
                row['tankmen'] = [{'tankmanID': 1}]
        with self.assertRaisesRegex(ValueError, 'foreign tankmen'):
            v.crew_flash(rows, False)

    def test_actual_ready_markers_do_not_hide_nonready_native_frame(self):
        rows = copy.deepcopy(self.rows)
        interval = self.report['process']['checks']['scenario']['intervals'][1]['native_interval']
        row = next(r for r in rows[interval['first_line']:interval['last_line'] - 1]
                   if r['event'] == 'native_hangar')
        row['vehicle_model_loaded'] = False
        with self.assertRaisesRegex(ValueError, 'non-ready native Hangar'):
            self.scenario(rows)

    def test_actual_connected_credit_change_outside_hold_is_rejected(self):
        rows = copy.deepcopy(self.rows)
        begin = self.transition['native_connected_lines'][1] - 1
        first_hold = self.report['process']['checks']['scenario']['intervals'][1]['native_interval']['first_line'] - 1
        candidates = [r for r in rows[begin:first_hold] if r['event'] == 'native_hangar' and r.get('items_cache_synced') is True]
        self.assertTrue(candidates)
        candidates[0]['resources']['credits'] += 1
        with self.assertRaisesRegex(ValueError, 'resources/statistics changed'):
            v.active_hangar(rows, 2, self.transition, self.expected[1])

    def test_actual_primary_return_cache_cannot_be_silently_replaced(self):
        sessions = copy.deepcopy(self.report['process']['sessions'])
        commands = sessions[2]['checks']['wire']['commands']
        for row in commands:
            if row.get('command') == 100:
                row['persistent_crc'] += 1
        checks = self.report['process']['checks']
        with self.assertRaisesRegex(ValueError, 'cache descriptors were not restored'):
            v.isolation(sessions, self.expected, checks['scenario'], checks['client_profile'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
