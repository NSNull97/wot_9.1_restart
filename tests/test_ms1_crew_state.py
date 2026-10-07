"""Crew snapshot preservation and hostile-input unit checks, not native proof.

The baseline is the actual immutable local r2 snapshot. Early delta-only unit
checks use labelled arbitrary UNIT sentinels. Later checks read root's real
native export; its mutation controls do not simulate a client constructor.
Forged documents are rejection controls. No client/service/DB is run here,
and generation does not prove native delivery, crew rendering or relogin.
"""
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import ms1_crew_state as crew


def raw_json(value):
    return (json.dumps(value, sort_keys=True, ensure_ascii=False, indent=2) + '\n').encode('utf-8')


def mutate_json(path, mutation):
    value = json.loads(path.read_bytes())
    mutation(value)
    path.write_bytes(raw_json(value))


class CrewSnapshotUnitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base_path = ROOT / 'local/server/fixtures/c5326cc1-8524-479c-8bba-72e973489c22/r2-catalog3'
        if not (cls.base_path / 'manifest.json').is_file():
            raise unittest.SkipTest('NOT_RUN: original immutable r2 snapshot required')
        cls.base = crew.validate_base(cls.base_path)
        cls.base_sha = crew.digest(cls.base['profile_raw'])
        cls.unit_export_sha = crew.digest(b'SYNTHETIC_UNIT_EXPORT_HASH_NOT_NATIVE')
        cls.timestamp = cls.base['profile']['test_grant']['granted_at_ms'] + 1000
        cls.profile = crew.promote_profile(cls.base['profile'], cls.base_sha,
                                          cls.unit_export_sha, cls.timestamp)
        cls.scratch = ROOT / 'local/evidence/20261005-p02-ms1-crew/data/state-unit-scratch'
        cls.scratch.mkdir(parents=True, exist_ok=True)

    def temporary(self):
        temporary = tempfile.TemporaryDirectory(dir=self.scratch)
        self.addCleanup(temporary.cleanup)
        return Path(temporary.name)

    def copy_base(self):
        path = self.temporary() / 'unit-copy-r2'
        shutil.copytree(self.base_path, path)
        return path

    def test_actual_base_is_verified_by_frozen_generator(self):
        self.assertEqual(crew.BASE_GENERATOR_SHA, crew.dependencies()['base_generator']['sha256'])
        self.assertEqual((2, 2, 1, 3), tuple(self.base['manifest'][key] for key in
                         ('profile_version', 'snapshot_revision', 'wire_sync_revision',
                          'compatibility_catalog_revision')))
        for name, raw in self.base['payloads'].items():
            self.assertEqual(raw, (self.base_path / name).read_bytes())

    def test_promotion_is_deterministic_and_changes_no_existing_identity_or_progress(self):
        before = deepcopy(self.base['profile'])
        result = crew.promote_profile(before, self.base_sha, self.unit_export_sha, self.timestamp)
        self.assertEqual(self.profile, result)
        self.assertEqual(self.base['profile'], before)
        for field in ('account_id', 'native_database_id', 'username', 'created_at_ms',
                      'resources', 'statistics', 'test_grant'):
            self.assertEqual(before[field], result[field], field)
        self.assertEqual(before['inventory'][1], result['inventory'][1])
        old_ms1 = deepcopy(result['inventory'][0])
        old_ms1['crew_assigned'] = False
        self.assertEqual(before['inventory'][0], old_ms1)
        self.assertEqual([before['account_id'] + ':ms1-commander-v1',
                          before['account_id'] + ':ms1-driver-v1'],
                         [row['crew_id'] for row in result['crew']])

    def test_foreign_identity_dates_resources_history_and_vehicle_delta_rejected(self):
        mutations = [lambda p: p.update(account_id='00000000-0000-4000-8000-000000000001'),
                     lambda p: p.update(native_database_id=p['native_database_id'] + 1),
                     lambda p: p.update(username='another_account'),
                     lambda p: p.update(created_at_ms=p['created_at_ms'] + 1),
                     lambda p: p['resources'].update(credits=p['resources']['credits'] + 1),
                     lambda p: p['statistics'].update(battles=1),
                     lambda p: p['inventory'][1].update(crew_assigned=True),
                     lambda p: p['inventory'][0].update(ammunition_count=1),
                     lambda p: p['test_grant'].update(grant_id='replaced-is7-grant'),
                     lambda p: p['crew'][0].update(vehicle_inventory_id=p['inventory'][1]['inventory_id']),
                     lambda p: p['crew'][1].update(role='loader'),
                     lambda p: p['crew'][1].update(skills=['repair'])]
        for index, mutation in enumerate(mutations):
            value = deepcopy(self.profile)
            mutation(value)
            with self.subTest(index=index), self.assertRaises(ValueError):
                crew.validate_profile(value, self.base['profile'], self.base_sha, self.unit_export_sha)

    def test_unknown_profile_keys_and_bool_int_substitutions_rejected(self):
        mutations = [lambda p: p.update(unexpected='unit'),
                     lambda p: p.update(profile_version=3.0),
                     lambda p: p.update(native_database_id=True),
                     lambda p: p['inventory'][0].update(crew_assigned=1),
                     lambda p: p['crew'][0].update(role_level=100.0),
                     lambda p: p['crew'][0].update(extra='unit'),
                     lambda p: p['resources'].update(gold=False),
                     lambda p: p['crew_grant'].update(granted_at_ms=True)]
        for index, mutation in enumerate(mutations):
            value = deepcopy(self.profile)
            mutation(value)
            with self.subTest(index=index), self.assertRaises(ValueError):
                crew.validate_profile(value, self.base['profile'], self.base_sha, self.unit_export_sha)

    def test_grant_timestamp_and_raw_base_provenance_are_exact(self):
        for stamp in (True, self.timestamp - 1001, 2147483648000, float(self.timestamp)):
            with self.subTest(stamp=stamp), self.assertRaises(ValueError):
                crew.promote_profile(self.base['profile'], self.base_sha, self.unit_export_sha, stamp)
        for base_sha, export_sha in ((crew.digest(self.base['profile_raw'] + b'\n'), self.unit_export_sha),
                                     (self.base_sha, '0' * 64)):
            with self.subTest(base=base_sha), self.assertRaises(ValueError):
                crew.validate_profile(self.profile, self.base['profile'], base_sha, export_sha)

    def unit_build(self):
        # Deliberately invalid native sentinels exercise only the encoder delta.
        data = {'crew': [{'compact_descr_hex': b'UNIT_ONLY_COMMANDER_NOT_NATIVE'.hex()},
                         {'compact_descr_hex': b'UNIT_ONLY_DRIVER_NOT_NATIVE'.hex()}]}
        return crew.build(self.base, self.profile, data)

    def test_encoder_delta_reversal_is_byte_exact_and_other_payloads_identical(self):
        old = deepcopy(self.base['trees'])
        model, compatibility, trees, preservation = self.unit_build()
        self.assertEqual(old, self.base['trees'])
        state = trees['state.bin']
        self.assertEqual(1, state['rev'])
        self.assertEqual([1, 2], state['inventory'][1]['crew'][1])
        self.assertEqual({1: 1, 2: 1}, state['inventory'][8]['vehicle'])
        self.assertEqual([None] * 5, state['inventory'][1]['crew'][2])
        reverse = deepcopy(state)
        reverse['inventory'][8] = {'compDescr': {}}
        reverse['inventory'][1]['crew'][1] = [None, None]
        self.assertEqual(self.base['payloads']['state.bin'], crew.legacy.encode_data(reverse))
        for name in ('shop.bin', 'dossier.bin'):
            self.assertEqual(self.base['payloads'][name], crew.legacy.encode_data(trees[name]))
        self.assertEqual(old['state.bin']['stats']['dossier'], state['stats']['dossier'])
        self.assertEqual(self.base['compatibility']['dossier_cache'], compatibility['dossier_cache'])
        self.assertEqual((3, 3), (model['profile_version'], model['snapshot_revision']))
        self.assertEqual('NOT_RUN', preservation['native_compatibility'])

    def test_existing_crew_is_never_overwritten(self):
        data = {'crew': [{'compact_descr_hex': b'UNIT_ONLY'.hex()}] * 2}
        for index in (1, 2):
            base = deepcopy(self.base)
            base['trees']['state.bin']['inventory'][1]['crew'][index][0] = 77
            with self.subTest(vehicle=index), self.assertRaises(ValueError):
                crew.build(base, self.profile, data)
        base = deepcopy(self.base)
        base['trees']['state.bin']['inventory'][8]['compDescr'][77] = b'UNIT_EXISTING_NOT_NATIVE'
        with self.assertRaises(ValueError):
            crew.build(base, self.profile, data)

    def test_preservation_retains_exact_existing_dossier_cursor_for_native_loader(self):
        preservation = self.unit_build()[3]
        self.assertEqual(self.base['manifest']['preservation']['dossier_cache'],
                         preservation.get('dossier_cache'))

    def test_base_manifest_identity_unknown_fields_and_bool_revision_are_rejected(self):
        mutations = [lambda p: p.update(account_id='00000000-0000-4000-8000-000000000001'),
                     lambda p: p.update(native_database_id=77),
                     lambda p: p.update(native_database_id=True),
                     lambda p: p.update(wire_sync_revision=True),
                     lambda p: p.update(unexpected='unit')]
        for index, mutation in enumerate(mutations):
            path = self.copy_base()
            mutate_json(path / 'manifest.json', mutation)
            with self.subTest(index=index), self.assertRaises(ValueError):
                crew.validate_base(path)

    def test_base_sidecar_boolean_identity_is_not_equal_to_integer_one(self):
        for name in ('fixture.json', 'compatibility.json'):
            path = self.copy_base()
            mutate_json(path / name, lambda value: value.update(native_database_id=True))
            with self.subTest(name=name), self.assertRaises(ValueError):
                crew.validate_base(path)

    def test_changed_base_payload_refused_even_if_its_declared_hash_is_recomputed(self):
        path = self.copy_base()
        tree = deepcopy(self.base['trees']['state.bin'])
        tree['stats']['credits'] += 1
        raw = crew.legacy.encode_data(tree)
        (path / 'state.bin').write_bytes(raw)
        def replace_hash(manifest):
            row = next(row for row in manifest['files'] if row['file'] == 'state.bin')
            row.update(bytes=len(raw), sha256=crew.digest(raw))
        mutate_json(path / 'manifest.json', replace_hash)
        with self.assertRaises(ValueError):
            crew.validate_base(path)

    def forged_export(self):
        """Known forged local evidence, only for an expected rejection test."""
        directory = self.temporary()
        _, paths = crew.config()
        module_spec = importlib.util.spec_from_file_location('crew_probe_unit_sources', ROOT / 'client_patch/ms1_crew_probe.py')
        probe = importlib.util.module_from_spec(module_spec)
        module_spec.loader.exec_module(probe)
        sources = []
        for relative, expected in probe.SOURCE_HASHES:
            source = paths['original_client_root'] / relative
            sources.append({'relative_path': relative, 'sha256': expected, 'bytes': source.stat().st_size})
        dossier = b'SYNTHETIC_UNIT_NOT_NATIVE_DOSSIER'
        data = dict(version=1, type_name='ussr:MS-1', type_id=[0, 13], vehicle_type_compact_descr=3329,
                    tankman_item_type=8, policy='test_lab_role_level_100_no_skills',
                    selection_unchanged=True, inventory_mutation_requested=False,
                    selection_before={'database_id': 1}, selection_after={'database_id': 1}, sources=sources,
                    tankman_dossier_hex=dossier.hex(), tankman_dossier_sha256=crew.digest(dossier), crew=[])
        for slot, role in enumerate(crew.ROLES):
            compact = ('SYNTHETIC_UNIT_' + role).encode() + dossier
            data['crew'].append(dict(slot_index=slot, role=role,
                compact_descr_hex=compact.hex(), compact_descr_bytes=len(compact),
                compact_descr_sha256=crew.digest(compact), dossier_sha256=crew.digest(dossier),
                original_parse_repack_equal=True, original_dossier_repack_equal=True,
                combined_roles=['commander', 'gunner', 'radioman', 'loader'] if slot == 0 else ['driver'],
                decoded=dict(nation_id=0, vehicle_type_id=13, role=role, role_level=100, free_xp=0,
                             last_skill_level=0, skills=[], is_premium=False, is_female=False)))
        plan = {'scope': 'SYNTHETIC_UNIT_NOT_NATIVE', 'sources': [
            {'path': 'client_patch/ms1_crew_probe.py', 'sha256': '0' * 64}]}
        plan_file = directory / 'UNIT-install-plan.json'
        plan_file.write_bytes(raw_json(plan))
        outcome = dict(scope='SYNTHETIC_UNIT_NOT_NATIVE', client_started=True, exit_code=0,
                       timed_out=False, restore='PASS', capture_status='PASS', exe_sha256=crew.EXE_SHA,
                       plan_sha256=crew.digest(plan_file.read_bytes()))
        outcome_file = directory / 'UNIT-outcome.json'
        outcome_file.write_bytes(raw_json(outcome))
        event = dict(data, event='ms1_crew_descriptors', elapsed_seconds=1)
        trace_file = directory / 'UNIT-forged-trace.jsonl'
        trace_file.write_bytes(json.dumps(event).encode() + b'\n')
        proof = {'record_index': 0}
        for key, file in (('trace', trace_file), ('install_plan', plan_file), ('outcome', outcome_file)):
            proof[key + '_file'], proof[key + '_sha256'] = str(file), crew.digest(file.read_bytes())
        export = directory / 'UNIT-forged-export.json'
        export.write_bytes(raw_json(dict(version=1, kind='native-ms1-crew', data=data, source=proof)))
        return export, trace_file

    def test_forged_native_proof_with_wrong_helper_hash_and_arbitrary_bytes_is_rejected(self):
        export, _ = self.forged_export()
        with self.assertRaises(ValueError):
            crew.validate_export(export)

    def test_changed_trace_with_stale_hash_and_foreign_proof_path_rejected(self):
        export, trace = self.forged_export()
        trace.write_bytes(trace.read_bytes() + b'\n')
        with self.assertRaises(ValueError):
            crew.validate_export(export)
        export, _ = self.forged_export()
        mutate_json(export, lambda p: p['source'].update(trace_file=str(ROOT / 'README.md')))
        with self.assertRaises(ValueError):
            crew.validate_export(export)

    def test_json_duplicate_fields_nonfinite_depth_and_size_are_rejected(self):
        path = self.temporary() / 'UNIT-json.json'
        for raw in (b'{"version":1,"version":1}', b'{"n":NaN}',
                    b'[' * 10 + b'0' + b']' * 10, b'"' + b'x' * 32768 + b'"'):
            path.write_bytes(raw)
            with self.subTest(length=len(raw)), self.assertRaises(ValueError):
                crew.read_json(path)

    def actual_export(self):
        path = ROOT / 'local/evidence/20261005-p02-ms1-crew/native-ms1-crew-export01.json'
        if not path.is_file():
            self.skipTest('NOT_RUN: actual root-run native crew export required; no substitute')
        return path, json.loads(path.read_bytes())

    def test_actual_export_validates_real_constructor_and_compilation_evidence(self):
        path, _ = self.actual_export()
        data, source = crew.validate_export(path)
        self.assertEqual(crew.digest(path.read_bytes()), source['sha256'])
        self.assertEqual([25, 25], [row['compact_descr_bytes'] for row in data['crew']])
        self.assertEqual([105030, 105030], [row['decoded']['total_xp'] for row in data['crew']])
        self.assertEqual([0, 0], [row['decoded']['free_xp'] for row in data['crew']])
        self.assertEqual([3, 2], [row['decoded']['rank_id'] for row in data['crew']])
        self.assertEqual(6, len(bytes.fromhex(data['tankman_dossier_hex'])))

    def test_actual_export_generates_fresh_immutable_snapshot_with_exact_preservation(self):
        native_path, _ = self.actual_export()
        export_sha = crew.digest(native_path.read_bytes())
        profile = crew.promote_profile(self.base['profile'], self.base_sha, export_sha, self.timestamp)
        directory = self.temporary()
        profile_path = directory / 'proposed-profile.json'
        profile_path.write_bytes(raw_json(profile))
        output = directory / 'r3-catalog3-unit-output'
        result = crew.generate(profile_path, self.base_path, native_path, output)
        self.assertEqual('NOT_RUN', result['native_compatibility'])
        manifest = json.loads((output / 'manifest.json').read_bytes())
        self.assertEqual(16, len(manifest))
        self.assertEqual((3, 3, 1, 3), tuple(manifest[key] for key in
                         ('profile_version', 'snapshot_revision', 'wire_sync_revision',
                          'compatibility_catalog_revision')))
        self.assertEqual(self.base['profile_raw'], (output / 'base-profile-input.json').read_bytes())
        self.assertEqual(profile_path.read_bytes(), (output / 'profile-input.json').read_bytes())
        for name in ('shop.bin', 'dossier.bin'):
            self.assertEqual(self.base['payloads'][name], (output / name).read_bytes())
        self.assertEqual(self.base['manifest']['grant'], manifest['grant'])
        self.assertEqual(self.base['manifest']['preservation']['dossier_cache'],
                         manifest['preservation']['dossier_cache'])
        before = {p.name: crew.digest(p.read_bytes()) for p in output.iterdir()}
        with self.assertRaises(ValueError):
            crew.generate(profile_path, self.base_path, native_path, output)
        self.assertEqual(before, {p.name: crew.digest(p.read_bytes()) for p in output.iterdir()})

    def test_actual_native_data_schema_types_and_passthrough_keys_rejected(self):
        _, original = self.actual_export()
        _, paths = crew.config()
        mutations = [lambda d: d.update(version=True), lambda d: d.update(type_id=[False, 13]),
                     lambda d: d.update(extra='unit'), lambda d: d['crew'][0].update(slot_index=False),
                     lambda d: d['crew'][0].update(extra='unit'),
                     lambda d: d['crew'][0]['decoded'].update(free_xp=False),
                     lambda d: d['crew'][0]['decoded'].update(first_name_id=True),
                     lambda d: d['crew'][0]['decoded'].update(rank_id=3.0),
                     lambda d: d['crew'][0]['decoded'].update(total_xp=105030.0),
                     lambda d: d['crew'][0]['decoded'].update(extra='unit'),
                     lambda d: d['selection_before'].update(database_id=True),
                     lambda d: d['selection_before'].update(selected_inventory_id=2.0),
                     lambda d: d['sources'][0].update(bytes=24558.0),
                     lambda d: d['sources'][0].update(extra='unit'),
                     lambda d: d['loaded_module_files'].update(tankmen='unit-foreign-module.pyc')]
        for index, mutation in enumerate(mutations):
            data = deepcopy(original['data'])
            mutation(data)
            with self.subTest(index=index), self.assertRaises(ValueError):
                crew._validate_native_crew_data(data, paths)

    def test_real_descriptor_prefix_mutations_are_rejected_even_with_updated_hash(self):
        _, original = self.actual_export()
        _, paths = crew.config()
        # Negative mutations of measured bytes; no constructor/encoder imitation.
        for offset in (0, 1, 2, 3, 4, 5, 6, 7, 9, 11, 13, 15, 19):
            data = deepcopy(original['data'])
            row = data['crew'][0]
            changed = bytearray.fromhex(row['compact_descr_hex'])
            changed[offset] ^= 1
            row['compact_descr_hex'] = changed.hex()
            row['compact_descr_sha256'] = crew.digest(changed)
            with self.subTest(offset=offset), self.assertRaises(ValueError):
                crew._validate_native_crew_data(data, paths)

    def test_played_or_foreign_dossier_is_not_accepted_as_empty(self):
        _, original = self.actual_export()
        _, paths = crew.config()
        for offset in (0, 2, 4):
            data = deepcopy(original['data'])
            changed = bytearray.fromhex(data['tankman_dossier_hex'])
            changed[offset] ^= 1
            data['tankman_dossier_hex'] = changed.hex()
            data['tankman_dossier_sha256'] = crew.digest(changed)
            with self.subTest(offset=offset), self.assertRaises(ValueError):
                crew._validate_native_crew_data(data, paths)

    def test_actual_trace_and_export_comparison_is_type_sensitive(self):
        _, envelope = self.actual_export()
        # All proof files stay exact. A JSON bool must not equal trace integer1.
        envelope['data']['version'] = True
        path = self.temporary() / 'UNIT-mutated-export.json'
        path.write_bytes(raw_json(envelope))
        with self.assertRaises(ValueError):
            crew.validate_export(path)

    def test_actual_prepared_producer_and_runtime_provenance_mismatch_rejected(self):
        _, envelope = self.actual_export()
        proof = envelope['source']
        directory = Path(proof['install_plan_file']).parent
        original_plan = json.loads(Path(proof['install_plan_file']).read_bytes())
        original_outcome = json.loads(Path(proof['outcome_file']).read_bytes())
        for mode in ('source', 'duplicate', 'relative_escape', 'outcome'):
            plan, outcome = deepcopy(original_plan), deepcopy(original_outcome)
            source = next(row for row in plan['sources'] if row['path'] == 'client_patch/ms1_crew_probe.py')
            if mode == 'source':
                source['sha256'] = '0' * 64
            elif mode == 'duplicate':
                plan['sources'].append(deepcopy(source))
            elif mode == 'relative_escape':
                source['compiled'] = '../native-ms1-crew-export01.json'
            else:
                next(row for row in outcome['source_provenance']['modules']
                     if row['module'] == 'ms1_crew_probe')['pyc_sha256'] = '0' * 64
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                crew._validate_compiled_probe(plan, directory, outcome)

    def test_prepared_bytecode_metadata_bundle_tampering_are_rejected(self):
        _, envelope = self.actual_export()
        original = Path(envelope['source']['install_plan_file']).parent
        plan = json.loads((original / 'install-plan.json').read_bytes())
        outcome = json.loads((original / 'native-outcome.json').read_bytes())
        paths = ('compiled/ms1_crew_probe.pyc', 'compiled/ms1_crew_probe.json',
                 'bundle/res_mods/0.9.1/scripts/client/ms1_crew_probe.pyc')
        for target in paths:
            directory = self.temporary()
            for relative in paths:
                destination = directory / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(original / relative, destination)
            modified = directory / target
            if target.endswith('.json'):
                mutate_json(modified, lambda data: data.update(source_sha256='0' * 64))
            else:
                data = bytearray(modified.read_bytes())
                data[-1] ^= 1
                modified.write_bytes(data)
            with self.subTest(target=target), self.assertRaises(ValueError):
                crew._validate_compiled_probe(plan, directory, outcome)

    def test_evidence_json_rejects_duplicate_overflow_and_structural_excess(self):
        for raw in (b'{"exit_code":0,"exit_code":0}', b'{"x":1e999}', b'{"x":NaN}',
                    b'[' * 14 + b'0' + b']' * 14,
                    json.dumps(list(range(257))).encode(), json.dumps({'x': 'x' * 8193}).encode()):
            with self.subTest(length=len(raw)), self.assertRaises(ValueError):
                crew._strict_evidence_json(raw, 65536)


if __name__ == '__main__':
    unittest.main()
