"""Verifier adversarial controls, never a synthetic native-compatibility claim."""
import copy
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import verify_test_garage as gate

E = ROOT / 'local/evidence/20261004-p02-hangar-ui'
FIXTURE = E / 'is7-generator/candidate-02/snapshot'
BASE = ROOT / 'local/server/fixtures/c5326cc1-8524-479c-8bba-72e973489c22/r1-catalog2'


def corrupt_literal(value):
    """Outgoing test data only; independently bounded parser reads it afterwards."""
    def one(item):
        if item is None:
            return b'N'
        if type(item) is bool:
            return b'\x88' if item else b'\x89'
        if type(item) is int:
            return b'J' + struct.pack('<i', item)
        if type(item) is float:
            return b'G' + struct.pack('>d', item)
        if type(item) is bytes:
            return b'T' + struct.pack('<I', len(item)) + item
        if type(item) in (tuple, list):
            values = b''.join(one(v) for v in item)
            return (b'(' + values + b't') if type(item) is tuple else (b'](' + values + b'e' if item else b']')
        if type(item) is dict:
            return b'}(' + b''.join(one(k) + one(v) for k, v in item.items()) + b'u' if item else b'}'
        raise TypeError(type(item).__name__)
    return b'\x80\x02' + one(value) + b'.'


def expected_vehicles():
    return {1: {'inventory_id': 1, 'type_compact_descr': 3329, 'type_name': 'ussr:MS-1',
                'health': 90, 'max_health': 90, 'xp': 0, 'crew_slots': 2}, 2: copy.deepcopy(gate.IS7_OBSERVED)}


def sample(seconds, number=1):
    return {'event': 'native_hangar', 'elapsed_seconds': seconds, 'observation_index': int(seconds) + 1,
            **gate.READY, 'vehicle': expected_vehicles()[number], 'selected_inventory_id': number,
            'views': {'main': {'class_name': 'LobbyView', 'alias': 'lobby', 'flash_bound': True, 'components': ['lobbyHeader']},
                      'lobby_sub': {'class_name': 'Hangar', 'alias': 'hangar', 'flash_bound': True, 'components': ['tankCarousel', 'params']}},
            'visual_entity_id': 123, 'vehicle_model_count': 4, 'vehicle_models_visible': [True] * 4}


class NativeObservationRejectionTests(unittest.TestCase):
    def setUp(self):
        self.expected = {'vehicles': expected_vehicles()}
        self.rows = [sample(i) for i in range(61)] + [sample(62, 2), sample(63, 2), sample(64, 1)]

    def test_control_spans_samples_and_real_selection_return(self):
        report = gate.garage_observations(self.rows, self.expected, 60)
        self.assertEqual('PASS', report['readiness']['status'])
        self.assertEqual(60, report['readiness']['continuous_seconds'])
        self.assertEqual('PASS', report['selection_cycle']['status'])

    def test_fifty_nine_seconds_is_fail_even_with_many_samples(self):
        rows = [sample(i / 10) for i in range(600)]
        self.assertEqual('FAIL', gate.garage_observations(rows, self.expected, 60)['readiness']['status'])

    def test_gap_or_loading_resets_ready_duration(self):
        for index in (29, 30):
            rows = copy.deepcopy(self.rows)
            rows[index]['waiting_visible'] = True
            self.assertEqual('FAIL', gate.garage_observations(rows, self.expected, 60)['readiness']['status'])
        rows = [r for r in self.rows if not 26 <= r['elapsed_seconds'] <= 31]
        self.assertEqual('FAIL', gate.garage_observations(rows, self.expected, 60)['readiness']['status'])

    def test_profile_before_sixty_cannot_be_rescued_by_later_hangar(self):
        rows = [sample(i) for i in range(130)]
        rows.insert(20, {'event': 'native_profile_call', 'phase': 'call', 'elapsed_seconds': 19.5})
        self.assertEqual('FAIL', gate.garage_observations(rows, self.expected, 60)['readiness']['status'])

    def test_switching_tanks_cannot_join_short_ready_segments(self):
        rows = [sample(i, 1 if i < 31 else 2) for i in range(70)]
        self.assertEqual('FAIL', gate.garage_observations(rows, self.expected, 60)['readiness']['status'])

    def test_unknown_inventory_wrong_hp_crew_or_xp_rejected(self):
        for key, value in (('health', 2149), ('crew_slots', 6), ('xp', 1), ('type_compact_descr', 3329)):
            rows = copy.deepcopy(self.rows)
            rows[61]['vehicle'][key] = value
            with self.assertRaisesRegex(ValueError, 'observed descriptor'):
                gate.garage_observations(rows, self.expected, 60)
        rows = copy.deepcopy(self.rows)
        rows[61]['selected_inventory_id'] = 3
        with self.assertRaisesRegex(ValueError, 'unknown native'):
            gate.garage_observations(rows, self.expected, 60)

    def test_one_vehicle_or_no_return_is_not_run_not_native_pass(self):
        self.assertEqual('NOT_RUN', gate.garage_observations(self.rows[:-1], self.expected, 60)['selection_cycle']['status'])
        self.assertEqual('NOT_RUN', gate.garage_observations(self.rows[:61], self.expected, 60)['selection_cycle']['status'])

    def test_unloaded_or_invisible_is7_is_not_displayed(self):
        rows = copy.deepcopy(self.rows)
        for row in rows[61:63]:
            row['vehicle_models_visible'][2] = False
        self.assertEqual('NOT_RUN', gate.garage_observations(rows, self.expected, 60)['selection_cycle']['status'])

    def test_cached_is7_start_can_return_via_ms1(self):
        rows = [sample(i, 2) for i in range(61)] + [sample(62), sample(63, 2)]
        self.assertEqual('PASS', gate.garage_observations(rows, self.expected, 60)['selection_cycle']['status'])

    def test_bool_hp_cannot_equal_numeric_state(self):
        rows = copy.deepcopy(self.rows)
        rows[1]['vehicle']['xp'] = False
        with self.assertRaises(ValueError):
            gate.garage_observations(rows, self.expected, 60)


@unittest.skipUnless(FIXTURE.exists() and BASE.exists(), 'NOT_RUN: actual immutable local fixtures unavailable')
class ActualFixtureDeltaTests(unittest.TestCase):
    def setUp(self):
        self.before = {n: (BASE / n).read_bytes() for n in ('state.bin', 'shop.bin', 'dossier.bin')}
        self.after = {n: (FIXTURE / n).read_bytes() for n in self.before}
        self.manifest = json.loads((FIXTURE / 'manifest.json').read_bytes())
        self.profile = json.loads((FIXTURE / 'profile-input.json').read_bytes())
        self.base_raw = (BASE / 'profile-input.json').read_bytes()
        self.native = json.loads((E / 'ui06-catalog2-manual-runtime/original-vehicle-is7.json').read_bytes())
        self.prices = {7169: (6100000, 0), **{value[1]: (value[-1], 0) for value in gate.COMPONENTS.values()}}
        self.seconds = self.profile['test_grant']['granted_at_ms'] // 1000

    def run_delta(self, raw=None):
        return gate.payload_delta(self.before, self.after if raw is None else raw, self.native, self.prices, self.seconds)

    def changed(self, name, change):
        raw = dict(self.after)
        tree = gate.entry.literal(raw[name])
        change(tree)
        raw[name] = corrupt_literal(tree)
        return raw

    def test_real_candidate_exact_delta_without_generator_execution(self):
        report = self.run_delta()
        self.assertEqual('PASS', report['status'])
        self.assertEqual({'version': 1, 'last_change_time': self.seconds, 'vehicle_type_compact_descr': 7169}, report['dossier_cache'])
        self.assertEqual(self.seconds, gate.profile_delta(self.base_raw, self.profile, self.manifest['grant']))

    def test_account_credit_or_old_ms1_changes_are_rejected(self):
        for change in (lambda t: t[b'stats'].__setitem__(b'credits', 999999),
                       lambda t: t[b'inventory'][1][b'repair'].__setitem__(1, (0, 89)),
                       lambda t: t[b'stats'].__setitem__(b'dossier', b'wrong')):
            with self.assertRaisesRegex(ValueError, 'MS-1/account'):
                self.run_delta(self.changed('state.bin', change))

    def test_grant_must_not_invent_ammo_crew_or_xp(self):
        for field, value in ((b'crew', [1, None, None, None, None]), (b'shells', [1]), (b'repair', (0, 2160))):
            with self.assertRaisesRegex(ValueError, 'IS-7 inventory'):
                self.run_delta(self.changed('state.bin', lambda t: t[b'inventory'][1][field].__setitem__(2, value)))
        with self.assertRaisesRegex(ValueError, 'IS-7 XP'):
            self.run_delta(self.changed('state.bin', lambda t: t[b'stats'][b'vehTypeXP'].__setitem__(7169, 5)))

    def test_unrelated_unlock_price_trade_or_inventory_rejected(self):
        mutations = [('state.bin', lambda t: t[b'stats'][b'unlocks'].append(999), 'unlock'),
                     ('state.bin', lambda t: t[b'inventory'][1][b'compDescr'].__setitem__(3, b'x'), 'inventory'),
                     ('shop.bin', lambda t: t[b'items'][b'itemPrices'].__setitem__(52486, (0, 0)), 'catalogue'),
                     ('shop.bin', lambda t: t[b'items'][b'itemPrices'].__setitem__(7169, (1, 0)), 'reference'),
                     ('shop.bin', lambda t: t[b'items'][b'notInShopItems'].remove(7169), 'unavailable')]
        for name, change, message in mutations:
            with self.assertRaisesRegex(ValueError, message):
                self.run_delta(self.changed(name, change))

    def test_wrong_dossier_inventory_id_or_time_or_history_rejected(self):
        correct = gate.entry.literal(self.after['dossier.bin'])
        row = correct[1][0]
        bad = [(1, [(2, row[1], row[2])]), (1, [(7169, row[1] - 1, row[2])]),
               (0, []), (1, [(7169, row[1], row[2][:-1] + b'\x01')])]
        for value in bad:
            with self.assertRaisesRegex(ValueError, 'dossier owner'):
                self.run_delta({**self.after, 'dossier.bin': corrupt_literal(value)})

    def test_cross_account_backdated_boolean_and_hash_profile_rejected(self):
        for key, value in (('account_id', '00000000-0000-0000-0000-000000000000'),
                           ('native_database_id', 2), ('created_at_ms', self.profile['created_at_ms'] + 1)):
            profile = copy.deepcopy(self.profile)
            profile[key] = value
            with self.assertRaisesRegex(ValueError, 'prior UUID'):
                gate.profile_delta(self.base_raw, profile, self.manifest['grant'])
        for key, value in (('granted_at_ms', True), ('granted_at_ms', 1), ('base_profile_sha256', '0' * 64)):
            grant = {**self.manifest['grant'], key: value}
            with self.assertRaisesRegex(ValueError, 'grant identity'):
                gate.profile_delta(self.base_raw, self.profile, grant)

    def test_real_original_resources_and_full_candidate_manifest(self):
        base_manifest = json.loads((BASE / 'manifest.json').read_bytes())
        ms1_display = gate.mo_literal('ussr_vehicles.mo', '8293bf404fa3bdbf724b3c4e8ac817c6f0bd9ba90a73ba27e8856d9b3b9bf7f1', 'MS-1')
        baseline = {'manifest': base_manifest, 'raw': self.before, 'vehicle': expected_vehicles()[1],
                    'account_id': self.profile['account_id'], 'native_id': self.profile['native_database_id'],
                    'name': self.profile['username'], 'vehicle_display_name': ms1_display,
                    'resources': self.profile['resources']}
        expected, proof = gate.garage_fixture(FIXTURE, BASE, baseline, ROOT / 'local')
        self.assertEqual('PASS', proof['status'])
        self.assertEqual(3, len(expected['raw']))
        self.assertEqual(7169, expected['dossier_cache']['vehicle_type_compact_descr'])
        self.assertEqual('ИС-7', expected['vehicle_display_names'][2]['value'])


class HeaderAndPhotoTests(unittest.TestCase):
    def setUp(self):
        self.expected = {'vehicles': expected_vehicles(), 'vehicle_display_names': {1: {'value': 'МС-1'}, 2: {'value': 'ИС-7'}}}

    def header(self, name, seconds):
        shared = {'event': 'native_header_call', 'method': 'as_setTankNameS', 'name': name,
                  'source': 'scripts/client/gui/Scaleform/daapi/view/meta/LobbyHeaderMeta.py', 'source_line': 202, 'flash_bound': True}
        return [{**shared, 'phase': 'call', 'elapsed_seconds': seconds},
                {**shared, 'phase': 'return', 'elapsed_seconds': seconds + .01, 'offset': 27}]

    def test_both_names_require_original_return_and_exact_source(self):
        rows = self.header('МС-1', 1) + self.header('ИС-7', 2)
        self.assertTrue(gate.tank_header(rows, self.expected)['both_vehicles'])
        for key, value in (('offset', 24), ('flash_bound', False), ('source', 'replacement.py'), ('name', 'FakeIS7')):
            changed = copy.deepcopy(rows)
            changed[-1][key] = value
            with self.assertRaises(ValueError):
                gate.tank_header(changed, self.expected)

    def test_unreturned_header_not_accepted(self):
        with self.assertRaisesRegex(ValueError, 'unreturned'):
            gate.tank_header(self.header('ИС-7', 1)[:1], self.expected)

    def photos(self):
        rows, images = [], []
        for number in (1, 2):
            row = sample(number * 10, number)
            rows.extend((sample(number * 10 - 2, number), sample(number * 10 - 1, number)))
            rows.append(row)
            rows.append({'event': 'vehicle_screenshot_requested', 'elapsed_seconds': number * 10 + .01,
                         'basename': 'vehicle_%d' % number, 'directory': str(ROOT / 'local/example/screenshots'),
                         'vehicle': copy.deepcopy(row['vehicle']), 'selected_inventory_id': number,
                         'observation_index': row['observation_index'], 'writer': 'BigWorld.screenShot',
                         'selection_changed_by_observer': False, 'model_loaded': True})
            images.append({'file': 'screenshots/vehicle_%d_001.png' % number,
                           'path': str(ROOT / 'local/example/screenshots' / ('vehicle_%d_001.png' % number)), 'sha256': str(number) * 64})
        return rows, images

    def test_native_photo_matches_observation_not_just_filename(self):
        rows, images = self.photos()
        self.assertEqual('PASS', gate.vehicle_photos(rows, images, self.expected)['status'])
        for key, value in (('observation_index', 999), ('model_loaded', False), ('selection_changed_by_observer', True), ('selected_inventory_id', 1)):
            wrong = copy.deepcopy(rows)
            wrong[-1][key] = value
            with self.assertRaises(ValueError):
                gate.vehicle_photos(wrong, images, self.expected)

    def test_wrong_photo_path_or_descriptor_rejected(self):
        rows, images = self.photos()
        rows[-1]['vehicle']['health'] = 99
        with self.assertRaisesRegex(ValueError, 'photographed descriptor'):
            gate.vehicle_photos(rows, images, self.expected)
        rows, images = self.photos()
        images[-1]['path'] = str(ROOT / 'local/wrong/vehicle_2_001.png')
        with self.assertRaisesRegex(ValueError, 'directory'):
            gate.vehicle_photos(rows, images, self.expected)

    def test_missing_photos_or_visual_stays_not_run(self):
        self.assertEqual('NOT_RUN', gate.vehicle_photos([], [], self.expected)['status'])
        self.assertEqual('NOT_RUN', gate.garage_visual(ROOT / 'local/nonexistent-review', 'a' * 64, {'status': 'NOT_RUN'})['status'])

    def test_review_requires_actual_both_hashes_attested_actions_and_findings(self):
        rows, images = self.photos()
        photos = gate.vehicle_photos(rows, images, self.expected)
        review = {'schema_version': 1, 'reviewer': 'root_visual_inspection', 'status': 'PASS', 'trace_sha256': 'a' * 64,
                  'human_attestation': {'source': 'direct_user_message', 'trace_sha256': 'a' * 64,
                      'statement': 'Synthetic adversarial test, not native proof.', 'actions': ['select_is7', 'return_to_ms1']},
                  'vehicle_reviews': [{'inventory_id': p['inventory_id'], 'observation_index': p['observation_index'],
                       'screenshot': {k: p[k] for k in ('file', 'sha256')}, 'trigger_source': 'human_attested',
                       'findings': {k: True for k in ('hangar_visible', 'vehicle_model_visible', 'correct_vehicle_name',
                                                     'player_identity_visible', 'resources_unchanged')}} for p in photos['photos']]}
        parent = ROOT / 'local/evidence/20261004-p02-hangar-ui/is7-verifier'
        parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=parent, prefix='unit-review-') as tmp:
            path = Path(tmp) / 'visual-review-garage.json'
            path.write_text(json.dumps(review), encoding='utf8')
            self.assertEqual('PASS', gate.garage_visual(Path(tmp), 'a' * 64, photos)['status'])
            for bad in ('hash', 'actions', 'findings'):
                changed = copy.deepcopy(review)
                if bad == 'hash':
                    changed['vehicle_reviews'][1]['screenshot']['sha256'] = 'e' * 64
                elif bad == 'actions':
                    changed['human_attestation']['actions'] = ['select_is7']
                else:
                    changed['vehicle_reviews'][1]['findings']['correct_vehicle_name'] = False
                path.write_text(json.dumps(changed), encoding='utf8')
                with self.assertRaises(ValueError):
                    gate.garage_visual(Path(tmp), 'a' * 64, photos)


class StatusBoundaryTests(unittest.TestCase):
    def test_missing_and_actual_invalid_evidence_have_distinct_status(self):
        def absent():
            raise FileNotFoundError('no actual run')
        def failed():
            raise ValueError('measured invalid bytes')
        self.assertEqual('NOT_RUN', gate.checked(absent)['status'])
        self.assertEqual('FAIL', gate.checked(failed)['status'])

    def test_current_failure_cannot_inherit_previous_success(self):
        self.assertEqual('FAIL', gate.paired_coverage('garage', {'garage': {'status': 'FAIL'}}, None, ROOT / 'local')['status'])
        self.assertEqual('NOT_RUN', gate.paired_coverage('garage', {'garage': {'status': 'NOT_RUN'}, 'relogin': {'status': 'NOT_RUN'}}, None, ROOT / 'local')['status'])

    def test_single_session_never_proves_cache_relogin(self):
        self.assertEqual('NOT_RUN', gate.relogin(None, {}, ROOT / 'local')['status'])


class PersistentHintParserTests(unittest.TestCase):
    def command(self, command, revision=0, a=0, b=0, request=1):
        return b'\x8e\x14\0' + struct.pack('<hhqii', request, command, revision, a, b)

    def test_actual_measured_ui09_metadata_requires_explicit_opt_in(self):
        account = self.command(100, a=-1176871600)
        shop = self.command(300, a=518, b=-846328027, request=2)
        for body in (account, shop):
            with self.assertRaises(ValueError):
                gate.entry.client_requests(body)
        values = gate.entry.client_requests(account + shop, cache_hints=True)
        self.assertEqual(-1176871600, values[0]['persistent_crc'])
        self.assertEqual(518, values[1]['cached_bytes'])
        self.assertEqual(-846328027, values[1]['cached_crc32_signed'])
        self.assertEqual(['sync', 'sync'], [v['kind'] for v in values])

    def test_advisory_changed_crc_never_becomes_input_state(self):
        for crc in (-2147483648, -1, 0, 2147483647):
            values = gate.entry.client_requests(self.command(100, a=crc) + self.command(300, a=1, b=crc, request=2), cache_hints=True)
            self.assertEqual(crc, values[0]['persistent_crc'])
            self.assertEqual(crc, values[1]['cached_crc32_signed'])
            self.assertFalse(any('state' in row or 'apply_cache' in row for row in values))

    def test_wrong_size_pair_reserved_revision_or_request_rejected(self):
        cases = [(100, 0, 3, 1, 1), (300, 0, -1, 0, 1), (300, 0, 0, 7, 1),
                 (300, 0, gate.entry.MAX_RAW + 65, 1, 1), (300, 3, 518, -1, 1),
                 (100, 2, -1, 0, 1), (100, 0, -1, 0, 0), (100, -1, 0, 0, 1),
                 (301, 0, 518, 1, 1)]
        for command, revision, a, b, request in cases:
            with self.assertRaises(ValueError):
                gate.entry.client_requests(self.command(command, revision, a, b, request), cache_hints=True)

    def test_cold_and_no_change_refresh_preserve_historical_shape(self):
        for command in (100, 300):
            old = gate.entry.client_requests(self.command(command))[0]
            new = gate.entry.client_requests(self.command(command), cache_hints=True)[0]
            self.assertEqual(old, {k: new[k] for k in old})
        old = gate.entry.client_requests(self.command(100, revision=1))[0]
        new = gate.entry.client_requests(self.command(100, revision=1), cache_hints=True)[0]
        self.assertEqual(old, {key: new[key] for key in old})

    def test_actual_ui10_cached_refresh_keeps_original_no_change_kind(self):
        body = self.command(100, 1, -1176871600, 0, 224)
        with self.assertRaises(ValueError):
            gate.entry.client_requests(body)
        parsed = gate.entry.client_requests(body, cache_hints=True)
        self.assertEqual({'kind': 'refresh', 'request': 224, 'command': 100, 'revision': 1,
                          'persistent_crc': -1176871600}, parsed[0])
        initial = gate.entry.client_requests(self.command(100, 0, -1176871600, 0, 220), cache_hints=True)
        sequence = gate.entry.persistent_hint_sequence(initial + parsed)
        self.assertEqual([224], sequence['refresh_requests'])

    def test_refresh_must_reuse_initial_hash_and_follow_initial_sync(self):
        initial = gate.entry.client_requests(self.command(100, 0, -1176871600, 0, 220), cache_hints=True)
        for crc in (0, -1176871601, 2147483647):
            refresh = gate.entry.client_requests(self.command(100, 1, crc, 0, 224), cache_hints=True)
            with self.assertRaisesRegex(ValueError, 'differs from initial'):
                gate.entry.persistent_hint_sequence(initial + refresh)
        correct = gate.entry.client_requests(self.command(100, 1, -1176871600, 0, 224), cache_hints=True)
        for rows in (correct, initial + initial + correct, correct + initial):
            with self.assertRaises(ValueError):
                gate.entry.persistent_hint_sequence(rows)
        with self.assertRaises(ValueError):
            gate.entry.client_requests(self.command(100, 1, -1176871600, 1, 224), cache_hints=True)

    def test_dossier_policy_and_bundle_limits_remain_strict(self):
        cursor = {'version': 1, 'last_change_time': 1791128141, 'vehicle_type_compact_descr': 7169}
        message = self.command(600, 1, cursor['last_change_time'], 0)
        self.assertEqual(1, gate.entry.client_requests(message, dossier_cache=cursor, cache_hints=True)[0]['revision'])
        with self.assertRaises(ValueError):
            gate.entry.client_requests(message, cache_hints=True)
        with self.assertRaises(ValueError):
            gate.entry.client_requests(self.command(100) * 17, cache_hints=True)
        with self.assertRaises(ValueError):
            gate.entry.client_requests(self.command(100)[:-1], cache_hints=True)
        with self.assertRaises(ValueError):
            gate.entry.client_requests(self.command(100), cache_hints=1)

    def test_full_stream_gateway_log_must_match_observed_descriptors(self):
        parent = E / 'is7-verifier'
        parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=parent, prefix='unit-cache-log-') as directory:
            path = Path(directory) / 'gateway-span.log'
            line = 'INITIAL_CACHE_HINT session=2 request=1 command=100 descriptor_a=-1176871600 descriptor_b=0 response=full_stream client_state_applied=false\n'
            raw = line.encode()
            path.write_bytes(raw)
            backend = {'source': str(path), 'source_sha256': gate.digest(raw), 'source_is_frozen_span': True, 'session_id': 2}
            wire = {'commands': gate.entry.client_requests(self.command(100, a=-1176871600), cache_hints=True)}
            self.assertEqual('PASS', gate.cache_hint_backend(backend, wire)['status'])
            for replacement in ('response=cache', 'client_state_applied=true', 'descriptor_a=-1176871601'):
                original = ('response=full_stream' if replacement.startswith('response') else
                            'client_state_applied=false' if replacement.startswith('client_state') else 'descriptor_a=-1176871600')
                changed = line.replace(original, replacement).encode()
                path.write_bytes(changed)
                backend['source_sha256'] = gate.digest(changed)
                with self.assertRaisesRegex(ValueError, 'advisory cache handling'):
                    gate.cache_hint_backend(backend, wire)

    def test_cached_refresh_log_is_bound_to_exact_request_and_no_change_response(self):
        parent = E / 'is7-verifier'
        with tempfile.TemporaryDirectory(dir=parent, prefix='unit-refresh-log-') as directory:
            path = Path(directory) / 'gateway-span.log'
            initial = 'INITIAL_CACHE_HINT session=2 request=220 command=100 descriptor_a=-1176871600 descriptor_b=0 response=full_stream client_state_applied=false\n'
            refresh = 'REFRESH_CACHE_HINT session=2 request=224 descriptor_a=-1176871600 descriptor_b=0 response=no_change client_state_applied=false\n'
            commands = gate.entry.client_requests(self.command(100, 0, -1176871600, 0, 220)
                                                  + self.command(100, 1, -1176871600, 0, 224), cache_hints=True)
            gate.entry.persistent_hint_sequence(commands)
            backend = {'source': str(path), 'source_is_frozen_span': True, 'session_id': 2}

            def evaluate(text):
                raw = text.encode()
                path.write_bytes(raw)
                backend['source_sha256'] = gate.digest(raw)
                return gate.cache_hint_backend(backend, {'commands': commands})

            self.assertEqual([{'request': 224, 'descriptor_a': -1176871600, 'descriptor_b': 0}],
                             evaluate(initial + refresh)['refresh_requests'])
            for wrong in ('', refresh + refresh, refresh.replace('request=224', 'request=225'),
                          refresh.replace('descriptor_a=-1176871600', 'descriptor_a=0'),
                          refresh.replace('descriptor_b=0', 'descriptor_b=1'),
                          refresh.replace('response=no_change', 'response=cache'),
                          refresh.replace('client_state_applied=false', 'client_state_applied=true')):
                with self.assertRaisesRegex(ValueError, 'cached refresh handling'):
                    evaluate(initial + wrong)


class PartialVisualTests(unittest.TestCase):
    def setUp(self):
        parent = E / 'is7-verifier'
        parent.mkdir(parents=True, exist_ok=True)
        directory = tempfile.TemporaryDirectory(dir=parent, prefix='unit-partial-')
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name).resolve()
        self.rows, self.images = [], []
        for event, call, basename in (('tooltip_screenshot_requested', 54, 'tooltip_ui_54_1'),
                                       ('profile_screenshot_requested', 164, 'profile_awards_ui_164_7')):
            self.rows.append({'event': event, 'call_id': call, 'writer': 'BigWorld.screenShot', 'original_hover_unchanged': True,
                              'basename': basename, 'directory': str(self.root / 'screenshots'), 'elapsed_seconds': call})
            self.images.append({'file': 'screenshots/' + basename + '_001.png', 'sha256': str(call)[0] * 64,
                                'path': str(self.root / 'screenshots' / (basename + '_001.png'))})
        self.review = {'schema_version': 2, 'reviewer': 'root_visual_inspection', 'trace_sha256': 'a' * 64, 'status': 'NOT_RUN',
                       'human_attestation': {'source': 'direct_user_message', 'trace_sha256': 'a' * 64,
                           'statement': 'Synthetic parser control, not native proof.',
                           'actions': ['hover_tooltip', 'open_awards', 'return_to_hangar']},
                       'tooltip_reviews': [], 'awards_reviews': [{'call_id': 164,
                           'screenshot': {k: self.images[1][k] for k in ('file', 'sha256')}, 'trigger_source': 'human_attested',
                           'findings': {'awards_tab_visible': True, 'native_catalog_visible': True, 'player_identity_visible': True}}],
                       'tooltip_capture_misses': [{'call_id': 54, 'screenshot': {k: self.images[0][k] for k in ('file', 'sha256')},
                                                   'finding': 'tooltip_not_visible_at_capture'}]}

    def evaluate(self):
        (self.root / 'visual-review-ui.json').write_text(json.dumps(self.review), encoding='utf8')
        return gate.gui_visual_review(self.rows, self.root, self.images, 'a' * 64,
                                      {'displays': []}, {'renders': [{'call_id': 164}]})

    def test_actual_awards_retained_without_claiming_absent_tooltip_pixels(self):
        report = self.evaluate()
        self.assertEqual('NOT_RUN', report['status'])
        self.assertEqual('PASS', report['checks']['awards_visual']['status'])
        self.assertEqual('NOT_RUN', report['checks']['tooltip_visual']['status'])
        self.assertEqual(54, report['observed_capture_misses'][0]['call_id'])

    def test_partial_coverage_cannot_be_declared_full_pass(self):
        self.review['status'] = 'PASS'
        with self.assertRaisesRegex(ValueError, 'contradicts measured'):
            self.evaluate()

    def test_negative_actual_awards_finding_is_fail_not_not_run(self):
        self.review['awards_reviews'][0]['findings']['native_catalog_visible'] = False
        self.review['status'] = 'FAIL'
        report = self.evaluate()
        self.assertEqual('FAIL', report['status'])
        self.assertEqual('FAIL', report['checks']['awards_visual']['status'])

    def test_typed_capture_miss_not_reclassified_as_complex_tooltip_display(self):
        self.review['tooltip_capture_misses'] = []
        self.review['tooltip_reviews'] = [{'call_id': 54, 'screenshot': {k: self.images[0][k] for k in ('file', 'sha256')},
            'trigger_source': 'human_attested', 'findings': {'tooltip_visible': True, 'matches_target': True, 'text_readable': True}}]
        self.review['status'] = 'PASS'
        with self.assertRaisesRegex(ValueError, 'verified original callback'):
            self.evaluate()

    def test_capture_miss_must_match_real_image_and_passive_marker(self):
        self.review['tooltip_capture_misses'][0]['screenshot']['sha256'] = 'f' * 64
        with self.assertRaisesRegex(ValueError, 'passive marker'):
            self.evaluate()
        self.review['tooltip_capture_misses'][0]['screenshot']['sha256'] = self.images[0]['sha256']
        self.rows[0]['original_hover_unchanged'] = False
        with self.assertRaisesRegex(ValueError, 'passive marker'):
            self.evaluate()


class PairedCacheTests(unittest.TestCase):
    """Synthetic parser controls only; these are not actual client sessions."""
    def setUp(self):
        parent = E / 'is7-verifier'
        parent.mkdir(parents=True, exist_ok=True)
        directory = tempfile.TemporaryDirectory(dir=parent, prefix='unit-pair-')
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name).resolve()
        before, after = self.root / 'before', self.root / 'after'
        before.mkdir()
        after.mkdir()
        (before / 'wire').mkdir()
        self.packet = before / 'wire/packet.bin'
        self.packet.write_bytes(b'synthetic parser control')
        plan = json.dumps({'settings': {'profile_dir': str(self.root / 'same-profile')}}).encode()
        (before / 'install-plan.json').write_bytes(plan)
        (after / 'install-plan.json').write_bytes(plan)
        capture = json.dumps({'packets': [{'file': 'packet.bin', 'bytes': self.packet.stat().st_size,
                                          'sha256': gate.digest(self.packet.read_bytes())}]}).encode()
        (before / 'wire/capture.json').write_bytes(capture)
        trace = before / 'trace.jsonl'
        trace.write_bytes(b'unit test trace, not a client trace')
        sources = [{'source': 'client_patch/' + name + '.py', 'source_sha256': 'a' * 64,
                    'pyc_sha256': 'b' * 64, 'installed_file': 'scripts/' + name + '.pyc'} for name in gate.ui.SOURCE_NAMES]
        self.previous = {'schema_version': gate.SCHEMA, 'tool': gate.TOOL, 'install': str(before), 'session_status': 'PASS',
            'checks': {'installation_plan': {'status': 'PASS', 'sha256': gate.digest(plan)}},
            'wire': {'status': 'PASS', 'capture_sha256': gate.digest(capture)}, 'backend': {'status': 'PASS', 'session_id': 1},
            'native_common': {'status': 'PASS', 'trace': {'path': str(trace), 'sha256': gate.digest(trace.read_bytes())},
                             'checks': {'compiled_sources': {'status': 'PASS', 'sources': sources}}},
            'native_hangar': {'status': 'PASS'}, 'visual': {'status': 'PASS'},
            'gui': {'status': 'PASS'}, 'garage': {'status': 'PASS'},
            'identity_snapshot': {'account_id': 'synthetic-test', 'vehicles': {'1': {'health': 90}, '2': {'health': 2150}},
                                  'dossier_cache': {'version': 1, 'last_change_time': 100, 'vehicle_type_compact_descr': 7169}},
            'process': {'started_utc': '2026-10-04T00:00:00+00:00', 'finished_utc': '2026-10-04T00:02:00+00:00',
                        'gateway_run': 'synthetic-run'}}
        self.current = copy.deepcopy(self.previous)
        self.current.update(install=str(after), gui={'status': 'NOT_RUN'}, garage={'status': 'NOT_RUN'})
        self.current['wire'].update(capture_sha256='c' * 64, commands=[{'command': 600, 'revision': 1, 'last_change_time': 100}])
        self.current['backend']['session_id'] = 2
        self.current['process'].update(started_utc='2026-10-04T00:03:00+00:00', finished_utc='2026-10-04T00:05:00+00:00')
        self.previous_path = self.root / 'previous-report.json'

    def pair(self):
        self.previous_path.write_text(json.dumps(self.previous), encoding='utf8')
        result = gate.relogin(self.previous_path, self.current, self.root)
        self.current['relogin'] = result
        return result

    def test_explicit_cached_cursor_and_immutable_pair_enable_previous_coverage(self):
        self.assertEqual('PASS', self.pair()['status'])
        self.assertEqual('PASS', gate.paired_coverage('garage', self.current, self.previous_path, self.root)['status'])
        self.assertEqual('PASS', gate.paired_coverage('gui', self.current, self.previous_path, self.root)['status'])

    def test_fresh_zero_cache_or_changed_time_does_not_prove_cache_persistence(self):
        for version, stamp in ((0, 0), (1, 99), (2, 100)):
            self.current['wire']['commands'] = [{'command': 600, 'revision': version, 'last_change_time': stamp}]
            with self.assertRaisesRegex(ValueError, 'persisted IS-7 dossier cursor'):
                self.pair()

    def test_another_native_profile_directory_rejects_persisted_cache_claim(self):
        path = Path(self.current['install']) / 'install-plan.json'
        path.write_text(json.dumps({'settings': {'profile_dir': str(self.root / 'other-profile')}}), encoding='utf8')
        with self.assertRaisesRegex(ValueError, 'cache directory'):
            self.pair()

    def test_actual_previous_packet_tampering_is_not_hidden_by_unchanged_manifest(self):
        self.packet.write_bytes(b'tampered captured bytes')
        with self.assertRaisesRegex(ValueError, 'previous packet evidence'):
            self.pair()

    def test_failed_or_unreviewed_session_does_not_pair(self):
        for field, status in (('native_common', 'FAIL'), ('visual', 'NOT_RUN')):
            self.previous[field]['status'] = status
            with self.assertRaisesRegex(ValueError, 'two clean native'):
                self.pair()
            self.previous[field]['status'] = 'PASS'

    def test_profile_or_compiled_source_change_rejected(self):
        self.current['identity_snapshot']['vehicles']['2']['health'] = 1
        with self.assertRaisesRegex(ValueError, 'immutable account'):
            self.pair()
        self.current['identity_snapshot'] = copy.deepcopy(self.previous['identity_snapshot'])
        self.current['native_common']['checks']['compiled_sources']['sources'][0]['pyc_sha256'] = 'e' * 64
        with self.assertRaisesRegex(ValueError, 'source/bytecode'):
            self.pair()

    def test_same_capture_or_session_id_is_not_relogin(self):
        self.current['wire']['capture_sha256'] = self.previous['wire']['capture_sha256']
        with self.assertRaisesRegex(ValueError, 'reused wire'):
            self.pair()
        self.current['wire']['capture_sha256'] = 'c' * 64
        self.current['backend']['session_id'] = 1
        with self.assertRaisesRegex(ValueError, 'same gateway'):
            self.pair()

    def test_previous_gui_pass_does_not_override_current_failure(self):
        self.assertEqual('PASS', self.pair()['status'])
        self.current['gui']['status'] = 'FAIL'
        self.assertEqual('FAIL', gate.paired_coverage('gui', self.current, self.previous_path, self.root)['status'])


if __name__ == '__main__':
    unittest.main()
