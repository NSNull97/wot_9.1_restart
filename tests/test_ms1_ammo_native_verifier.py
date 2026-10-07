"""Parser controls only; synthetic inputs do not establish native compatibility."""
import hashlib
import copy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from verify_ms1_ammo_native import literal_ammo, public_control, state_ammo_delta, OTHER_OPERATIONS
import verify_ms1_ammo_native as verifier


def key(first=5891, second=5892):
    return b'(' + b'J' + struct.pack('<i', first) + b'J' + struct.pack('<i', second) + b't'


class BoundedAmmoLiteralTests(unittest.TestCase):
    def test_observed_tuple_shape_with_six_int_layout(self):
        # Literal constructed independently of any production state encoder.
        counts = [2570, 20, 2826, 0, 3082, 0]
        payload = b'\x80\x02}(' + key() + b'](' + b''.join(b'J' + struct.pack('<i', x) for x in counts) + b'eu.'
        self.assertEqual(literal_ammo(payload), {(5891, 5892): counts})

    def test_frozen_profile3_payloads_still_parse(self):
        directory = ROOT / 'local/server/fixtures/c5326cc1-8524-479c-8bba-72e973489c22/r3-catalog3'
        if not directory.is_dir():
            self.skipTest('Actual frozen local profile3 corpus unavailable')
        pins = {'state.bin': '186518109966a093397a0602e69653886bc8093c082ec35782278f539bc32120',
                'shop.bin': 'b8bd4a9c23a5b58c28d0838a5eab5c3f99c707ce2d496dd3747f9fb8e344c467',
                'dossier.bin': 'eb1fa654c81a9888885752278e426308274b1007bd27da6b03128b77759afa09'}
        from verify_hangar import literal
        for name, pin in pins.items():
            with self.subTest(name=name):
                raw = (directory / name).read_bytes()
                self.assertEqual(hashlib.sha256(raw).hexdigest(), pin)
                self.assertEqual(literal_ammo(raw), literal(raw))

    def test_duplicate_tuple_key_rejected(self):
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            literal_ammo(b'\x80\x02}(' + key() + b'K\x14' + key() + b'K\x15u.')

    def test_wrong_tuple_key_shapes_rejected(self):
        for wrong in (b')', b'(K\x01t', b'(K\x01K\x02K\x03t', b'(\x88K\x02t',
                      b'(U\x01xK\x02t', key(0, 5892), key(-1, 5892), key(65536, 5892)):
            with self.subTest(raw=wrong), self.assertRaisesRegex(ValueError, 'key type/bound'):
                literal_ammo(b'\x80\x02}(' + wrong + b'K\x14u.')

    def test_bool_key_does_not_alias_integer(self):
        with self.assertRaisesRegex(ValueError, 'key type/bound'):
            literal_ammo(b'\x80\x02}(\x88K\x00u.')

    def test_unsafe_and_unmeasured_opcodes_rejected(self):
        for opcode in (b'c', b'R', b'b', b'i', b'o', b'q', b'h', b'\x81', b'\x86', b'V'):
            with self.subTest(opcode=opcode), self.assertRaisesRegex(ValueError, 'forbidden'):
                literal_ammo(b'\x80\x02' + opcode + b'.')

    def test_size_protocol_and_string_bounds(self):
        for wrong in (b'', b'\x80\x03}.', b'\x80\x02U\xffx.',
                      b'\x80\x02T\xff\xff\xff\xff.', b'\x80\x02}' + b'N' * 16384 + b'.'):
            with self.subTest(size=len(wrong)), self.assertRaises(ValueError):
                literal_ammo(wrong)


class AmmoPublicMetadataTests(unittest.TestCase):
    def outcome(self, operation='verify'):
        value = dict.fromkeys(OTHER_OPERATIONS, False)
        value.update(bytes=600, credentials_present=True, plaintext_recorded=False,
                     submit_via='python', screenshot_when=None,
                     export_ms1_ammo=operation == 'export', verify_ms1_ammo=operation == 'verify',
                     quit_when='ms1_ammo_exported' if operation == 'export' else 'ms1_ammo_observed')
        return {'diagnostic_control': value}

    def test_two_disjoint_operations(self):
        for operation in ('export', 'verify'):
            self.assertEqual(len(public_control(self.outcome(operation), operation)), 15)

    def test_private_fields_and_digests_rejected(self):
        for name in ('sha256', 'password', 'username', 'alternate_password', 'ms1_ammo_expected'):
            wrong = self.outcome()
            wrong['diagnostic_control'][name] = 'UNIT_ONLY_NONSECRET'
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'exact public'):
                public_control(wrong)

    def test_mode_and_bounds_not_truthy_coerced(self):
        for name, value in [('bytes', True), ('bytes', 8193), ('bytes', 0), ('plaintext_recorded', 0),
                            ('credentials_present', 1), ('export_ms1_ammo', True), ('verify_ms1_ammo', 1),
                            ('quit_when', 'long_hangar_observed'), ('verify_account_switch', True)]:
            wrong = self.outcome()
            wrong['diagnostic_control'][name] = value
            with self.subTest(name=name, value=value), self.assertRaises(ValueError):
                public_control(wrong)


class AmmoStateDeltaTests(unittest.TestCase):
    def states(self):
        # The synthetic shape tests a narrow delta. It is not a native fixture.
        old = {b'rev': 1, b'stats': {b'credits': 100000, b'dossier': b'own-unit-bytes'},
               b'inventory': {1: {b'shells': {1: [], 2: []}, b'shellsLayout': {1: {}, 2: {}},
                                    b'crew': {1: [1, 2], 2: [None] * 5}},
                               8: {b'compDescr': {1: b'unit-commander', 2: b'unit-driver'}}}}
        new = copy.deepcopy(old)
        flat = [2570, 20, 2826, 0, 3082, 0]
        new[b'inventory'][1][b'shells'][1] = flat[:]
        new[b'inventory'][1][b'shellsLayout'][1] = {(5891, 5892): flat[:]}
        return old, new

    def check(self, old, new, flat=None, layout=None):
        return state_ammo_delta(old, new, [2570, 20, 2826, 0, 3082, 0] if flat is None else flat,
                                (5891, 5892) if layout is None else layout)

    def test_only_twenty_ap_fields_pass(self):
        old, new = self.states()
        self.assertEqual(self.check(old, new)['total'], 20)

    def test_no_foreign_or_overflowing_shells(self):
        for flat in ([2570, 97, 2826, 0, 3082, 0], [2570, -1, 2826, 0, 3082, 0],
                     [2570, 20, 2826, False, 3082, 0], [2571, 20, 2826, 0, 3082, 0],
                     [2826, 20, 2570, 0, 3082, 0]):
            old, new = self.states()
            with self.subTest(flat=flat), self.assertRaises(ValueError):
                self.check(old, new, flat=flat)

    def test_changed_resources_and_crew_fail(self):
        for field in ('credits', 'dossier', 'crew', 'tankman', 'is7_shells', 'layout_gun', 'layout_count'):
            old, new = self.states()
            if field == 'credits': new[b'stats'][b'credits'] += 1
            elif field == 'dossier': new[b'stats'][b'dossier'] += b'x'
            elif field == 'crew': new[b'inventory'][1][b'crew'][1] = [2, 1]
            elif field == 'tankman': new[b'inventory'][8][b'compDescr'][1] += b'x'
            elif field == 'is7_shells': new[b'inventory'][1][b'shells'][2] = [2570, 20]
            elif field == 'layout_gun': new[b'inventory'][1][b'shellsLayout'][1] = {(5891, 5893): [2570, 20, 2826, 0, 3082, 0]}
            else: new[b'inventory'][1][b'shellsLayout'][1][(5891, 5892)][1] = 19
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.check(old, new)

    def test_previous_grant_cannot_be_overwritten(self):
        old, new = self.states()
        old[b'inventory'][1][b'shells'][1] = [2570, 1]
        with self.assertRaises(ValueError):
            self.check(old, new)

    def test_node_and_depth_bounds(self):
        for wrong in (b'\x80\x02](' + b'N' * 4096 + b'e.',
                      b'\x80\x02' + b'(' * 17 + b'N' + b't' * 17 + b'.'):
            with self.subTest(size=len(wrong)), self.assertRaisesRegex(ValueError, 'bound'):
                literal_ammo(wrong)

    def test_nonfinite_and_trailing_input_rejected(self):
        for wrong in (b'\x80\x02}.N', b'\x80\x02NN.', b'\x80\x02}(',
                      b'\x80\x02G' + struct.pack('>d', float('nan')) + b'.',
                      b'\x80\x02G' + struct.pack('>d', float('inf')) + b'.'):
            with self.subTest(size=len(wrong)), self.assertRaises(ValueError):
                literal_ammo(wrong)

    def test_container_mismatch_and_odd_dict_rejected(self):
        for wrong in (b'\x80\x02}(K\x01u.', b'\x80\x02](K\x01K\x02u.',
                      b'\x80\x02}(K\x01e.', b'\x80\x02e.'):
            with self.subTest(raw=wrong), self.assertRaises(ValueError):
                literal_ammo(wrong)


class ActualReadonlyAmmoCorpus(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = ROOT / 'local/server/fixtures/c5326cc1-8524-479c-8bba-72e973489c22/r3-catalog3'
        cls.export_path = ROOT / 'local/evidence/20261005-p02-ms1-ammo/native-ms1-ammo-export01.json'
        if not cls.directory.exists() or not cls.export_path.exists():
            raise unittest.SkipTest('Frozen local native export/reference fixture unavailable')
        cls.state = literal_ammo((cls.directory / 'state.bin').read_bytes())
        cls.data = json.loads(cls.export_path.read_text('utf8'))['data']
        cls.expected = {'state': cls.state, 'native_id': 1}

    def loaded_unit_observation(self):
        # Mutation of an actual pre-grant observation is a UNIT parser input,
        # never passed off as populated native compatibility evidence.
        value = copy.deepcopy(self.data)
        value.pop('sources')
        value['observation_index'] = 1
        selected = {'database_id': 1, 'selected_inventory_id': 1,
                    'selected_descriptor_sha256': hashlib.sha256(self.state[b'inventory'][1][b'compDescr'][1]).hexdigest()}
        value['selection_before'] = selected
        value['selection_after'] = dict(selected)
        item = value['observation']
        item.update(raw_shells=verifier.FLAT[:], raw_layouts=[{'layout_index': [5891, 5892], 'shells': verifier.FLAT[:]}],
                    mounted_layout_present=True, native_loaded_pairs=[[2570, 20], [2826, 0], [3082, 0]],
                    native_layout_rows=[[2570, 20, False], [2826, 0, False], [3082, 0, False]],
                    ammo_sum=20, default_ammo_sum=20, is_ammo_full=True)
        item['gui_shells'][0].update(count=20, default_count=20, default_layout_value=[2570, 20])
        return value

    def test_actual_original_export_can_read_ms1_while_is7_selected(self):
        observed = verifier.ammo_observation(self.data, self.expected, loaded=False, selected_ms1=False)
        self.assertEqual(observed['ammo_sum'], 0)
        self.assertEqual(self.data['selection_before']['selected_inventory_id'], 2)

    def test_actual_export_is_not_a_populated_grant(self):
        with self.assertRaises(ValueError):
            verifier.ammo_observation(self.data, self.expected)

    def test_twenty_not_ninety_six_even_when_fullness_flag_true(self):
        observed = verifier.ammo_observation(self.loaded_unit_observation(), self.expected)
        self.assertEqual(observed['ammo_sum'], 20)
        self.assertEqual(observed['ammo_max_size'], 96)
        self.assertTrue(observed['is_ammo_full'])

    def test_getter_raw_layout_disagreement_rejected(self):
        for field in ('raw_shells', 'raw_layouts', 'native_loaded_pairs', 'native_layout_rows', 'gui_shells'):
            wrong = self.loaded_unit_observation()
            item = wrong['observation']
            if field == 'raw_shells': item[field][1] = 19
            elif field == 'raw_layouts': item[field][0]['shells'][1] = 19
            elif field in ('native_loaded_pairs', 'native_layout_rows'): item[field][0][1] = 19
            else: item[field][0]['count'] = 19
            with self.subTest(field=field), self.assertRaises(ValueError):
                verifier.ammo_observation(wrong, self.expected)

    def test_booleans_spare_stock_autoload_and_foreign_identity_rejected(self):
        for field in ('version', 'max_ammo', 'database_id', 'count', 'inventory_count', 'storage', 'auto_load', 'layout_currency'):
            wrong = self.loaded_unit_observation()
            if field in ('version', 'max_ammo'): wrong[field] = True
            elif field == 'database_id': wrong['selection_before'][field] = 2
            elif field in ('count', 'inventory_count'): wrong['observation']['gui_shells'][0][field] = True
            elif field == 'storage': wrong['observation']['storage_shells'] = [{'compact_descr': 2570, 'count': 1}]
            elif field == 'auto_load': wrong['observation']['is_auto_load'] = True
            else: wrong['observation']['native_layout_rows'][0][2] = True
            with self.subTest(field=field), self.assertRaises(ValueError):
                verifier.ammo_observation(wrong, self.expected)

    def test_actual_profile4_raw_splice_and_unrelated_corruption(self):
        new_file = self.directory.parent / 'r4-catalog3/state.bin'
        if not new_file.exists(): self.skipTest('Actual generated profile4 snapshot unavailable')
        old, new = (self.directory / 'state.bin').read_bytes(), new_file.read_bytes()
        self.assertEqual(verifier.exact_state_bytes(old, new)['restored_sha256'], hashlib.sha256(old).hexdigest())
        verifier.state_ammo_delta(self.state, literal_ammo(new), verifier.FLAT, verifier.LAYOUT)
        for wrong in (new + b'\0', new.replace(b'\x80\x02', b'\x80\x03', 1), new.replace(b'credits', b'Credits', 1)):
            with self.assertRaises(ValueError): verifier.exact_state_bytes(old, wrong)

    def test_actual_export_source_mismatch_rejected(self):
        wrong = copy.deepcopy(self.data)
        wrong['sources'][0]['sha256'] = '0' * 64
        with self.assertRaises(ValueError):
            verifier.ammo_observation(wrong, self.expected, loaded=False, selected_ms1=False)


class AmmoFlashArgumentControls(unittest.TestCase):
    def data(self):
        return {'gunName': 'UNIT GUN', 'maxAmmo': 96, 'defaultAmmoCount': 20, 'vehicleLocked': False,
                'stateMsg': '', 'stateLevel': 'info', 'stateWarning': 0,
                'shells': [{'id': str(s[2]), 'type': s[3], 'label': 'UNIT SHELL', 'icon': 'unit.png',
                            'count': n, 'historicalBattleID': None} for s, n in zip(verifier.SHELLS, (20, 0, 0))]}

    def test_exact_count_projection_only(self):
        self.assertEqual(verifier.flash_ammo_data(self.data())['total'], 20)

    def test_forged_or_missing_shell_counts_rejected(self):
        for field in ('count', 'id', 'type', 'maxAmmo', 'defaultAmmoCount', 'missing', 'extra'):
            wrong = self.data()
            if field == 'count': wrong['shells'][0]['count'] = 96
            elif field == 'id': wrong['shells'][0]['id'] = '2571'
            elif field == 'type': wrong['shells'][0]['type'] = 'HIGH_EXPLOSIVE'
            elif field in ('maxAmmo', 'defaultAmmoCount'): wrong[field] = True
            elif field == 'missing': wrong['shells'].pop()
            else: wrong['unknown'] = 'UNIT'
            with self.subTest(field=field), self.assertRaises(ValueError): verifier.flash_ammo_data(wrong)


class BuildEvidenceControls(unittest.TestCase):
    def test_actual_complete_source_manifest_and_negative_shapes(self):
        path = ROOT / 'local/evidence/20261005-p02-ms1-ammo/server-rebuild-01/source-manifest.json'
        if not path.exists(): self.skipTest('Actual local build evidence unavailable')
        actual = json.loads(path.read_text('utf8'))
        self.assertEqual(len(verifier.source_manifest_rows(actual)), 79)
        for field in ('duplicate', 'path', 'bool_size', 'missing_dependency', 'oversized'):
            wrong = copy.deepcopy(actual)
            if field == 'duplicate': wrong['files'].append(dict(wrong['files'][0]))
            elif field == 'path': wrong['files'][0]['relative_path'] = '../outside.rs'
            elif field == 'bool_size': wrong['files'][0]['bytes'] = True
            elif field == 'missing_dependency':
                wrong['files'] = [r for r in wrong['files'] if r['relative_path'] != 'local/vendor/wg-toolkit-rs/serde-pickle/Cargo.toml']
            else: wrong['files'][0]['bytes'] = 4 * 1024 * 1024
            with self.subTest(field=field), self.assertRaises(ValueError): verifier.source_manifest_rows(wrong)

    def timeline(self):
        start = datetime(2026, 10, 5, tzinfo=timezone.utc)
        t = [(start + timedelta(seconds=n)).isoformat() for n in range(13)]
        return ({'captured_utc': t[0]}, {'captured_utc': t[1], 'state': {'utc': '2000-01-01T00:00:00+00:00'}},
                {'started_utc': t[2], 'finished_utc': t[3]}, {'started_utc': t[4], 'finished_utc': t[5]},
                {'captured_utc': t[6]}, {'started_utc': t[7], 'finished_utc': t[8]}, {'captured_utc': t[9]},
                {'captured_utc': t[10]}, {'started_utc': t[11], 'finished_utc': t[12]})

    def test_wrapper_capture_time_not_stale_state_time(self):
        self.assertTrue(verifier.build_chronology(*self.timeline())['stop_uses_capture_utc_not_stale_state_utc'])

    def test_out_of_order_or_naive_time_rejected(self):
        for field in ('early_client', 'stop_after_build', 'naive'):
            rows = copy.deepcopy(self.timeline())
            if field == 'early_client': rows[-1]['started_utc'] = rows[0]['captured_utc']
            elif field == 'stop_after_build': rows[1]['captured_utc'] = rows[-1]['finished_utc']
            else: rows[-1]['started_utc'] = '2026-10-05T00:00:11'
            with self.subTest(field=field), self.assertRaises(ValueError): verifier.build_chronology(*rows)

    def test_actual_pregrant_export_cannot_use_new_gateway_build(self):
        path = ROOT / 'local/evidence/20261005-p02-ms1-ammo/export01-prepare/native-outcome.json'
        if not path.exists() or not (verifier.DEFAULT_BUILD / 'after.json').exists():
            self.skipTest('Actual pre-grant export/build evidence unavailable')
        outcome = json.loads(path.read_text('utf8'))
        with self.assertRaisesRegex(ValueError, 'native run used another gateway build'):
            verifier.backend_build(verifier.DEFAULT_BUILD, outcome, verifier.config()[1]['local_artifacts_root'])


class PairedCacheBoundaryControls(unittest.TestCase):
    """Wrapper invariants on synthetic metadata; never native acceptance."""
    def session(self, index, account_crc):
        cursor = {'version': 1, 'last_change_time': 100, 'vehicle_type_compact_descr': 7169}
        commands = [{'kind': 'sync', 'command': 100, 'persistent_crc': account_crc},
                    {'kind': 'sync', 'command': 300, 'cached_bytes': 518, 'cached_crc32_signed': -88},
                    {'kind': 'sync', 'command': 600, 'revision': 1, 'last_change_time': 100},
                    {'kind': 'refresh', 'command': 100, 'persistent_crc': account_crc}]
        return {'status': 'PASS', 'original_install': str(ROOT / 'local/unit-only' / str(index)),
                'identity_snapshot': {'account_id': 'UNIT', 'profile_sha256': 'UNIT_PROFILE', 'dossier_cache': cursor},
                'original': {'trace': {'sha256': 'UNIT_TRACE_' + str(index)}},
                'checks': {'installation': {'started_utc': '2026-10-05T00:0%d:00+00:00' % index,
                                             'finished_utc': '2026-10-05T00:0%d:30+00:00' % index,
                                             'artifacts': {'native-outcome.json': {'sha256': 'UNIT_OUTCOME_' + str(index)}}},
                           'client_profile': {'directory': str(ROOT / 'local/unit-only/shared-profile')},
                           'compiled_sources': {'modules': ['UNIT_SAME_SOURCES']},
                           'backend_build': {'executable_sha256': 'UNIT_SAME_IMAGE'},
                           'wire': {'status': 'PASS', 'commands': commands}, 'cache': {'status': 'PASS'},
                           'scenario': {'fingerprint': 'UNIT_SAME_AUTHORITATIVE_AMMO'}}}

    def test_account_cache_may_advance_after_authoritative_grant(self):
        before, now = self.session(1, -11), self.session(2, -22)
        proof = verifier.relogin(now, before)
        self.assertTrue(proof['account_hint_change_observed'])
        self.assertTrue(proof['real_cached_relogin'])

    def test_refresh_must_equal_own_initial_not_other_session(self):
        before, now = self.session(1, -11), self.session(2, -22)
        now['checks']['wire']['commands'][-1]['persistent_crc'] = -11
        with self.assertRaisesRegex(ValueError, 'refresh descriptor'):
            verifier.relogin(now, before)

    def test_empty_cache_or_changed_shop_cursor_or_profile_rejected(self):
        for field in ('empty', 'shop', 'dossier', 'profile', 'ammo', 'source', 'directory', 'same_install'):
            before, now = self.session(1, -11), self.session(2, -22)
            if field == 'empty':
                now['checks']['wire']['commands'][0]['persistent_crc'] = 0
                now['checks']['wire']['commands'][-1]['persistent_crc'] = 0
            elif field == 'shop': now['checks']['wire']['commands'][1]['cached_crc32_signed'] -= 1
            elif field == 'dossier': now['checks']['wire']['commands'][2]['last_change_time'] += 1
            elif field == 'profile': now['identity_snapshot']['profile_sha256'] = 'UNIT_OTHER_PROFILE'
            elif field == 'ammo': now['checks']['scenario']['fingerprint'] = 'UNIT_DIFFERENT_AMMO'
            elif field == 'source': now['checks']['compiled_sources']['modules'].append('UNIT_OTHER_CODE')
            elif field == 'directory': now['checks']['client_profile']['directory'] += '-other'
            else: now['original_install'] = before['original_install']
            with self.subTest(field=field), self.assertRaises(ValueError): verifier.relogin(now, before)

    def test_overlap_or_reused_native_trace_rejected(self):
        for field in ('overlap', 'trace'):
            before, now = self.session(1, -11), self.session(2, -22)
            if field == 'overlap': now['checks']['installation']['started_utc'] = before['checks']['installation']['started_utc']
            else: now['original']['trace']['sha256'] = before['original']['trace']['sha256']
            with self.subTest(field=field), self.assertRaises(ValueError): verifier.relogin(now, before)


class ActualScenarioAndFlashControls(unittest.TestCase):
    """Closed original native rows, mutated only in RAM for negative controls."""
    @classmethod
    def setUpClass(cls):
        cls.evidence = ROOT / 'local/evidence/20261005-p02-ms1-ammo'
        cls.install = cls.evidence / 'ammo01-prepare'
        if not (cls.install / 'native-outcome.json').exists():
            raise unittest.SkipTest('Closed ammunition native corpus unavailable')
        cls.local_root = ROOT / 'local'
        cls.plan, cls.outcome, cls.rows, cls.original, _ = verifier.artifacts(cls.install, cls.local_root)
        proof = json.loads((cls.evidence / 'wire/fixture-checks-01/result.json').read_text('utf8'))['fixture']
        fixture = Path(proof['fixture'])
        cls.public = proof['public_snapshot']
        cls.expected = {'state': literal_ammo((fixture / 'state.bin').read_bytes()),
                        'native_id': proof['native_database_id'], 'resources': cls.public['resources'],
                        'profile': json.loads((fixture / 'profile-input.json').read_text('utf8')),
                        'name': cls.public['name']}
        cls.life = verifier.lifecycle(cls.rows, cls.plan, cls.outcome)
        cls.scenario = verifier.scenario(cls.rows, cls.plan, cls.expected, cls.public, cls.life, cls.local_root)

    def scenario_gate(self, rows):
        return verifier.scenario(rows, self.plan, self.expected, self.public, self.life, self.local_root)

    def test_actual_waiting_arm_before_login_is_not_ready_evidence(self):
        start = next(i for i, r in enumerate(self.rows) if r['event'] == 'ms1_ammo_start')
        self.assertLess(start + 1, self.life['connected_line'])
        self.assertGreater(self.scenario['continuous_ready']['first_line'], self.life['account_constructor_lines'][1])
        self.assertEqual(self.scenario['observations'], 3)
        self.assertGreaterEqual(self.scenario['continuous_ready']['observed_duration_seconds'], 15)

    def test_pre_auth_or_after_fini_observations_rejected(self):
        for event, destination in (('ms1_ammo_state', 'before_account'),
                                   ('ms1_ammo_observation', 'before_account'),
                                   ('ms1_ammo_snapshot', 'after_fini'),
                                   ('ms1_ammo_action', 'before_account')):
            rows = copy.deepcopy(self.rows)
            index = next(i for i, r in enumerate(rows) if r['event'] == event)
            item = rows.pop(index)
            if destination == 'before_account':
                index = self.life['connected_line'] - 1
            else:
                index = len(rows)
            rows.insert(index, item)
            with self.subTest(event=event, destination=destination), self.assertRaises(ValueError):
                self.scenario_gate(rows)

    def test_arm_must_follow_control_consumption(self):
        rows = copy.deepcopy(self.rows)
        index = next(i for i, r in enumerate(rows) if r['event'] == 'ms1_ammo_start')
        item = rows.pop(index)
        consumed = next(i for i, r in enumerate(rows) if r['event'] == 'test_control_consumed')
        rows.insert(consumed, item)
        with self.assertRaisesRegex(ValueError, 'constructed Account lifetime'):
            self.scenario_gate(rows)

    def test_actual_windows_review_path_case_and_wrong_image(self):
        self.assertEqual(verifier.visual(self.install, self.original['trace']['sha256'], self.scenario)['status'], 'PASS')
        wrong = copy.deepcopy(self.scenario)
        wrong['images'][0]['file'] = 'another_native_image.png'
        wrong['images'][0]['path'] = str(Path(wrong['images'][0]['path']).with_name('another_native_image.png'))
        with self.assertRaisesRegex(ValueError, 'another image'):
            verifier.visual(self.install, self.original['trace']['sha256'], wrong)

    def test_actual_original_parent_meta_projection_matches(self):
        result = verifier.native_ammo_flash(self.rows, self.scenario)
        self.assertTrue(result['projections'])
        self.assertTrue(all(p['projection']['total'] == 20 for p in result['projections']))

    def test_original_parent_return_cannot_disagree_with_meta(self):
        rows = copy.deepcopy(self.rows)
        parent = next(r for r in rows if r['event'] == 'native_ammo_call' and r['phase'] == 'return'
                      and r['method'] == '__updateAmmo' and r['data']['maxAmmo'] == 96)
        parent['data']['shells'][0]['count'] = 19
        with self.assertRaisesRegex(ValueError, 'returned ammunition differs'):
            verifier.native_ammo_flash(rows, self.scenario)

    def test_original_initial_call_and_return_offsets_are_exact_ints(self):
        for method, phase, offset in (('as_setAmmoS', 'call', 12345), ('__updateAmmo', 'call', 0),
                                      ('as_setAmmoS', 'call', -1.0), ('__updateAmmo', 'return', 504.0),
                                      ('as_setAmmoS', 'return', 27.0)):
            rows = copy.deepcopy(self.rows)
            row = next(r for r in rows if r['event'] == 'native_ammo_call' and r['method'] == method
                       and r['phase'] == phase)
            row['offset'] = offset
            with self.subTest(method=method, phase=phase, offset=offset), self.assertRaises(ValueError):
                verifier.native_ammo_flash(rows, self.scenario)


if __name__ == '__main__':
    unittest.main()
