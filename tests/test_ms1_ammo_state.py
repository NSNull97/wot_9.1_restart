"""Profile4/domain/primitive bounds, with actual old fixtures read only.

Synthetic grant digests/contract rows in unit tests are NOT native export proof.
The separately guarded actual-export tests require a completed original-client
run. No tests launch clients, change server state or modify historical fixtures.
"""
from copy import deepcopy
import json
import os
from pathlib import Path
import pickletools
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import ms1_ammo_state as ammo


class EncoderBoundsTests(unittest.TestCase):
    def mounted(self, key=(5891, 5892)):
        return {'inventory': {1: {'shellsLayout': {1: {key: list(ammo.LOADED)}}}}}

    def test_legacy_primitives_are_exact(self):
        for value in [None, True, False, -2147483648, 2147483647, 0, 256, 65536,
                      1.25, b'\xff', 'Танкист_Ёж', [], {}, (), (0, []),
                      {'label': {1: [None, b'UNIT_ONLY']}}]:
            with self.subTest(type=type(value).__name__):
                self.assertEqual(ammo.legacy.encode_data(value), ammo.encode_data(value))

    def test_only_measured_mounted_tuple_key_is_accepted(self):
        raw = ammo.encode_data(self.mounted())
        names = {op.name for op, _, _ in pickletools.genops(raw)}
        self.assertIn('TUPLE', names)
        self.assertLessEqual(names, {'PROTO', 'EMPTY_DICT', 'MARK', 'SHORT_BINSTRING',
            'BININT1', 'BININT2', 'EMPTY_LIST', 'APPENDS', 'SETITEMS', 'TUPLE', 'STOP'})
        with self.assertRaises(ValueError):
            ammo.legacy.encode_data(self.mounted())
        for value in [{(5891, 5892): []}, {'inventory': {2: {'shellsLayout': {1: {(5891, 5892): []}}}}},
                      self.mounted((5891, 5893)), self.mounted((5891, 5892, 0)),
                      self.mounted((5891.0, 5892)), self.mounted((True, 5892))]:
            with self.subTest(value=repr(value)), self.assertRaises(ValueError):
                ammo.encode_data(value)

    def test_bytes_labels_have_identical_measured_path(self):
        value = {b'inventory': {1: {b'shellsLayout': {1: {(5891, 5892): list(ammo.LOADED)}}}}}
        self.assertEqual(ammo.encode_data(self.mounted()), ammo.encode_data(value))

    def test_no_python_object_methods_or_unsafe_opcodes(self):
        class RefuseMethods:
            def __reduce__(self):
                raise AssertionError('object hook must never execute')
        for value in [RefuseMethods(), {False: 1}, {frozenset(): 1}, {'a': 1, b'a': 2},
                      2147483648, float('nan'), float('inf')]:
            with self.subTest(kind=type(value).__name__), self.assertRaises(ValueError):
                ammo.encode_data(value)

    def test_size_depth_cycle_node_bounds(self):
        cycle = []; cycle.append(cycle)
        deep = []; p = deep
        for _ in range(17):
            child = []; p.append(child); p = child
        for value in [cycle, deep, [0] * 4096, b'x' * 16384, [b'x' * 8192, b'y' * 8192]]:
            with self.subTest(kind=type(value).__name__), self.assertRaises(ValueError):
                ammo.encode_data(value)


class ProfileAndDeltaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = ROOT / 'local/server/fixtures/c5326cc1-8524-479c-8bba-72e973489c22/r3-catalog3'
        if not (cls.directory / 'manifest.json').is_file():
            raise unittest.SkipTest('NOT_RUN: actual immutable accepted profile3 is absent')
        cls.base = ammo.validate_base(cls.directory)
        cls.base_sha = ammo.digest(cls.base['profile_raw'])
        cls.export_sha = ammo.digest(b'UNIT_ONLY_NATIVE_EXPORT_NOT_RUN')
        cls.stamp = cls.base['profile']['crew_grant']['granted_at_ms'] + 1000
        cls.profile = ammo.promote_profile(cls.base['profile'], cls.base_sha, cls.export_sha, cls.stamp)

    def test_exact_accepted_base_payloads_and_sources(self):
        self.assertEqual(ammo.CREW_GENERATOR_SHA, ammo.dependencies()['base_generator']['sha256'])
        for name, raw in self.base['payloads'].items():
            self.assertEqual((self.directory / name).read_bytes(), raw)
            self.assertEqual(ammo.encode_data(self.base['trees'][name]), raw)

    def test_domain_delta_is_exact_and_does_not_mutate_input(self):
        before = deepcopy(self.base['profile'])
        p = ammo.promote_profile(before, self.base_sha, self.export_sha, self.stamp)
        self.assertEqual(before, self.base['profile'])
        self.assertEqual(p, self.profile)
        self.assertEqual(ammo.validate_profile(p, before, self.base_sha, self.export_sha), p)
        reverse = deepcopy(p)
        del reverse['ammunition']; del reverse['ammo_grant']
        reverse.update(profile_version=3, snapshot_revision=3)
        reverse['inventory'][0]['ammunition_count'] = 0
        self.assertEqual(reverse, before)
        self.assertEqual(20, p['inventory'][0]['ammunition_count'])
        self.assertNotIn('native', ''.join(p['ammunition'][0]))

    def test_foreign_progress_inventory_crew_and_provenance_rejected(self):
        changes = [lambda p: p.update(profile_version=True), lambda p: p.update(extra=1),
            lambda p: p.update(native_database_id=True), lambda p: p.update(username='other_account'),
            lambda p: p.update(created_at_ms=p['created_at_ms'] + 1),
            lambda p: p['resources'].update(credits=p['resources']['credits'] + 1),
            lambda p: p['statistics'].update(battles=1), lambda p: p['crew'][0].update(role_level=99),
            lambda p: p['crew_grant'].update(granted_at_ms=p['crew_grant']['granted_at_ms'] + 1),
            lambda p: p['inventory'][1].update(ammunition_count=20),
            lambda p: p['inventory'][0].update(crew_assigned=False),
            lambda p: p['ammunition'][0].update(vehicle_inventory_id=p['inventory'][1]['inventory_id']),
            lambda p: p['ammunition'][0].update(shell_definition_id='shell:foreign'),
            lambda p: p['ammunition'].append(deepcopy(p['ammunition'][0])),
            lambda p: p['ammunition'][0].update(native_shell_id=2570),
            lambda p: p['ammo_grant'].update(native_export_sha256='0' * 64),
            lambda p: p['ammo_grant'].update(base_profile_sha256='0' * 64)]
        for change in changes:
            p = deepcopy(self.profile); change(p)
            with self.subTest(value=repr(p['ammo_grant'])), self.assertRaises(ValueError):
                ammo.validate_profile(p, self.base['profile'], self.base_sha, self.export_sha)

    def test_count_and_timestamps_are_own_bounded_policy(self):
        for count in (True, -1, 0, 19, 20.0, 96, 97, 2147483648):
            p = deepcopy(self.profile)
            p['ammunition'][0]['count'] = count; p['inventory'][0]['ammunition_count'] = count
            with self.subTest(count=count), self.assertRaises(ValueError):
                ammo.validate_profile(p, self.base['profile'], self.base_sha, self.export_sha)
        for stamp in (True, float(self.stamp), self.stamp - 1001, 2147483648000):
            with self.subTest(stamp=stamp), self.assertRaises(ValueError):
                ammo.promote_profile(self.base['profile'], self.base_sha, self.export_sha, stamp)

    def test_primitive_base_fields_cannot_smuggle_invalid_profile3(self):
        for mutate in [lambda p: p['resources'].update(gold=False), lambda p: p['statistics'].update(wins=True),
                       lambda p: p['crew'][0].update(role_level=100.0),
                       lambda p: p['inventory'][1].update(health=0),
                       lambda p: p['inventory'][0].update(ammunition_count=20)]:
            p = deepcopy(self.base['profile']); mutate(p)
            with self.assertRaises(ValueError):
                ammo.promote_profile(p, self.base_sha, self.export_sha, self.stamp)

    def unit_contract(self):
        # Labels and numeric contract are static facts; this is not a trace or
        # substitute native export and cannot pass generate/validate_export.
        return dict(max_ammo=96, turret={'compact_descr': 5891}, gun={'compact_descr': 5892},
                    shells=[{'compact_descr': value} for value in (2570, 2826, 3082)])

    def test_inverse_shells_delta_restores_all_accepted_state_bytes(self):
        before = deepcopy(self.base['trees'])
        model, compat, trees, preservation = ammo.build(self.base, self.profile, self.unit_contract())
        self.assertEqual(before, self.base['trees'])
        state = trees['state.bin']
        self.assertEqual(ammo.LOADED, state['inventory'][1]['shells'][1])
        self.assertEqual({(5891, 5892): ammo.LOADED}, state['inventory'][1]['shellsLayout'][1])
        self.assertEqual({1, 8}, set(state['inventory']))
        reverse = deepcopy(state)
        reverse['inventory'][1]['shells'][1] = []
        reverse['inventory'][1]['shellsLayout'][1] = {}
        self.assertEqual(self.base['payloads']['state.bin'], ammo.encode_data(reverse))
        self.assertEqual(self.base['trees']['state.bin']['stats']['dossier'], state['stats']['dossier'])
        self.assertEqual(1, state['rev'])
        for name in ('shop.bin', 'dossier.bin'):
            self.assertEqual(self.base['payloads'][name], ammo.encode_data(trees[name]))
        self.assertEqual(self.base['compatibility']['dossier_cache'], compat['dossier_cache'])
        self.assertEqual(self.base['compatibility']['crew_mapping'], compat['crew_mapping'])
        self.assertEqual('NOT_RUN', preservation['native_compatibility'])
        self.assertEqual((4, 4), (model['profile_version'], model['snapshot_revision']))

    def test_wrong_mounted_module_capacity_compatible_shell_or_existing_load_refused(self):
        for mutation in [lambda p: p.update(max_ammo=92),
                         lambda p: p['gun'].update(compact_descr=1),
                         lambda p: p['shells'][0].update(compact_descr=999)]:
            data = self.unit_contract(); mutation(data)
            with self.assertRaises(ValueError):
                ammo.build(self.base, self.profile, data)
        changed = deepcopy(self.base)
        changed['trees']['state.bin']['inventory'][1]['shells'][1] = [2570, 1]
        with self.assertRaises(ValueError):
            ammo.build(changed, self.profile, self.unit_contract())

    def test_actual_base_tampering_is_rejected_before_any_new_snapshot(self):
        root = ROOT / 'local/evidence/20261005-p02-ms1-ammo/data/unit-scratch'
        root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=root) as temporary:
            path = Path(temporary) / 'r3-copy'; shutil.copytree(self.directory, path)
            manifest = json.loads((path / 'manifest.json').read_bytes())
            for mutation in [lambda p: p.update(native_database_id=True),
                             lambda p: p.update(extra=1),
                             lambda p: p['preservation'].update(base_state_sha256='0' * 64),
                             lambda p: p['generator'].update(sha256='0' * 64)]:
                value = deepcopy(manifest); mutation(value)
                (path / 'manifest.json').write_text(json.dumps(value), encoding='utf8')
                with self.assertRaises(ValueError):
                    ammo.validate_base(path)
            (path / 'manifest.json').write_text(json.dumps(manifest), encoding='utf8')
            original = (path / 'state.bin').read_bytes()
            (path / 'state.bin').write_bytes(original[:-1] + b'N')
            with self.assertRaises(ValueError):
                ammo.validate_base(path)

    def test_no_synthetic_export_can_create_output(self):
        root = ROOT / 'local/evidence/20261005-p02-ms1-ammo/data/unit-scratch'
        root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=root) as temporary:
            path = Path(temporary)
            (path / 'profile.json').write_text(json.dumps(self.profile), encoding='utf8')
            (path / 'unit-not-native.json').write_text(json.dumps({'purpose': 'UNIT_NOT_NATIVE'}), encoding='utf8')
            with self.assertRaises(ValueError):
                ammo.generate(path / 'profile.json', self.directory, path / 'unit-not-native.json', path / 'output')
            self.assertFalse((path / 'output').exists())


class ActualNativeExportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = os.environ.get('MS1_AMMO_TEST_EXPORT')
        if not path or not (ROOT / path).is_file():
            raise unittest.SkipTest('NOT_RUN: MS1_AMMO_TEST_EXPORT must name actual closed native evidence')
        cls.path = (ROOT / path).resolve()
        cls.data, cls.source = ammo.validate_export(cls.path)
        cls.envelope = json.loads(cls.path.read_bytes())
        cls.base = ammo.validate_base(ROOT / 'local/server/fixtures/c5326cc1-8524-479c-8bba-72e973489c22/r3-catalog3')
        cls.profile = ammo.promote_profile(cls.base['profile'], ammo.digest(cls.base['profile_raw']),
                                          cls.source['sha256'], cls.base['profile']['crew_grant']['granted_at_ms'] + 1000)
        cls.scratch = ROOT / 'local/evidence/20261005-p02-ms1-ammo/data/native-export-test-scratch'
        cls.scratch.mkdir(parents=True, exist_ok=True)

    def temporary(self):
        temporary = tempfile.TemporaryDirectory(dir=self.scratch)
        self.addCleanup(temporary.cleanup)
        return Path(temporary.name)

    def test_actual_original_trace_source_compilation_and_contract(self):
        self.assertEqual(96, self.data['max_ammo'])
        self.assertEqual([2570, 2826, 3082], [row['compact_descr'] for row in self.data['shells']])
        self.assertEqual([], self.data['observation']['raw_shells'])
        self.assertEqual([], self.data['observation']['raw_layouts'])
        self.assertEqual(False, self.data['inventory_mutation_requested'])
        self.assertEqual(ammo.digest(self.path.read_bytes()), self.source['sha256'])

    def test_actual_proof_generates_only_fresh_bound_snapshot(self):
        temporary = self.temporary()
        path, out = temporary / 'profile4.json', temporary / 'r4-catalog3'
        path.write_text(json.dumps(self.profile, ensure_ascii=False), encoding='utf8')
        before = {file.name: ammo.digest(file.read_bytes()) for file in self.base['directory'].iterdir()}
        result = ammo.generate(path, self.base['directory'], self.path, out)
        self.assertEqual('NOT_RUN', result['native_compatibility'])
        manifest = json.loads((out / 'manifest.json').read_bytes())
        self.assertEqual(16, len(manifest))
        self.assertEqual((4, 4, 4, 1, 3), tuple(manifest[k] for k in
            ('fixture_version', 'profile_version', 'snapshot_revision', 'wire_sync_revision', 'compatibility_catalog_revision')))
        self.assertEqual(self.profile['test_grant'], manifest['grant'])
        for name in ('shop.bin', 'dossier.bin'):
            self.assertEqual(self.base['payloads'][name], (out / name).read_bytes())
        self.assertEqual(before, {file.name: ammo.digest(file.read_bytes()) for file in self.base['directory'].iterdir()})
        with self.assertRaises(ValueError):
            ammo.generate(path, self.base['directory'], self.path, out)

    def test_full_envelope_changed_event_hash_and_unknown_fields_refused(self):
        path = self.temporary() / 'false-proof.json'
        for change in [lambda p: p.update(version=True), lambda p: p.update(extra=1),
                       lambda p: p['data'].update(max_ammo=92),
                       lambda p: p['source'].update(trace_sha256='0' * 64),
                       lambda p: p['source'].update(record_index=True)]:
            value = deepcopy(self.envelope); change(value)
            path.write_text(json.dumps(value), encoding='utf8')
            with self.assertRaises(ValueError):
                ammo.validate_export(path)

    def test_native_data_rejects_wrong_mount_shell_source_preload_or_side_effect(self):
        _, paths = ammo.config()
        for change in [lambda d: d.update(vehicle_inventory_id=True),
                       lambda d: d.update(selection_unchanged=1),
                       lambda d: d.update(inventory_mutation_requested=True),
                       lambda d: d.update(native_empty_ammo=[2570, 20]),
                       lambda d: d['gun'].update(compact_descr=1),
                       lambda d: d['shells'][0].update(compact_descr=999),
                       lambda d: d['sources'][0].update(sha256='0' * 64),
                       lambda d: d['observation'].update(raw_shells=[2570, 20]),
                       lambda d: d['observation'].update(is_auto_load=True),
                       lambda d: d['observation']['gui_shells'][0].update(count=1)]:
            value = deepcopy(self.data); change(value)
            with self.assertRaises(ValueError):
                ammo._validate_native_ammo_data(value, paths)

    def test_compiled_producer_is_pinned_not_whichever_file_now_exists(self):
        proof = self.envelope['source']
        plan_path = Path(proof['install_plan_file'])
        plan = json.loads(plan_path.read_bytes()); outcome = json.loads(Path(proof['outcome_file']).read_bytes())
        ammo._validate_compiled_probe(plan, plan_path.parent, outcome)
        for change in [lambda r: r.update(sha256='0' * 64),
                       lambda r: r.update(compiled='../outside.pyc')]:
            altered = deepcopy(plan)
            row = next(r for r in altered['sources'] if r['path'] == 'client_patch/ms1_ammo_probe.py')
            change(row)
            with self.assertRaises((ValueError, FileNotFoundError)):
                ammo._validate_compiled_probe(altered, plan_path.parent, outcome)


if __name__ == '__main__':
    unittest.main()
