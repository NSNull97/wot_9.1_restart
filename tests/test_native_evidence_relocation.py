"""Immutable actual-proof relocation and hostile mapping controls; no client run."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import native_evidence_relocation as subject
import ms1_crew_state as crew
import ms1_ammo_state as ammo


class NativeEvidenceRelocationTests(unittest.TestCase):
    def setUp(self):
        parent = ROOT / 'local/tests/native-evidence-relocation'
        parent.mkdir(parents=True, exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(dir=parent)
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.exports = {}
        for kind in ('crew', 'ammo'):
            source = ROOT / f'local/evidence/20261005-p02-ms1-{kind}/native-ms1-{kind}-export01.json'
            sidecar = Path(str(source) + subject.SUFFIX)
            if not sidecar.is_file():
                self.fail('Required actual export relocation missing; run native_evidence_relocation.py for ' + kind)
            manifest = json.loads(sidecar.read_bytes())
            destination = self.directory / source.name
            shutil.copyfile(source, destination)
            shutil.copyfile(sidecar, str(destination) + subject.SUFFIX)
            for row in manifest['files']:
                target = self.directory / row['file']; target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source.parent / row['file'], target)
            self.exports[kind] = destination

    def manifest(self, kind='crew'):
        return Path(str(self.exports[kind]) + subject.SUFFIX)

    def resolve(self, kind='crew'):
        path = self.exports[kind]
        return subject.for_export(path, path.read_bytes())

    def test_actual_exports_preserve_original_digest_and_full_native_validation(self):
        for kind, module in (('crew', crew), ('ammo', ammo)):
            with self.subTest(kind=kind):
                path = self.exports[kind]; before = path.read_bytes()
                data, source = module.validate_export(path)
                self.assertEqual(source['sha256'], subject.CHECKPOINTS['native-ms1-' + kind][0])
                self.assertEqual(before, path.read_bytes())
                self.assertFalse(data['inventory_mutation_requested'])
                self.assertEqual(source['file'], str(path))

    def test_absent_sidecar_retains_old_strict_root_boundary(self):
        self.manifest().unlink()
        self.assertIsNone(self.resolve())
        with self.assertRaisesRegex(ValueError, 'below local'):
            crew.validate_export(self.exports['crew'])

    def test_sidecar_rejects_unknown_duplicate_missing_and_escaping_mappings(self):
        path = self.manifest(); original = json.loads(path.read_bytes())
        changes = [lambda m: m.update(version=True), lambda m: m.update(extra=1),
                   lambda m: m['export'].update(sha256='0' * 64),
                   lambda m: m['files'].pop(), lambda m: m['files'].append(deepcopy(m['files'][0])),
                   lambda m: m['files'][0].update(role='unknown'),
                   lambda m: m['files'][1].update(role='trace'),
                   lambda m: m['files'][0].update(file='../outside.json'),
                   lambda m: m['files'][0].update(file=str(self.exports['crew'])),
                   lambda m: m['files'][0].update(file='noncanonical\\trace.json'),
                   lambda m: m['files'][0].update(file='./trace.json'),
                   lambda m: m['files'][0].update(bytes=True),
                   lambda m: m['files'][0].update(sha256='0' * 64),
                   lambda m: m['files'][0].update(source=str(self.directory / 'unrelated.json')),
                   lambda m: m['source_roots'].update(original=str(self.directory)),
                   lambda m: m['target_roots'].update(original=str(self.directory))]
        for index, change in enumerate(changes):
            value = deepcopy(original); change(value); path.write_bytes(subject.canonical(value))
            with self.subTest(index=index), self.assertRaises((ValueError, FileNotFoundError)):
                self.resolve()

    def test_every_copied_artifact_is_hash_checked(self):
        manifest = json.loads(self.manifest().read_bytes())
        for row in manifest['files']:
            path = self.directory / row['file']; original = path.read_bytes()
            path.write_bytes(original + b'changed')
            with self.subTest(role=row['role']), self.assertRaises(ValueError):
                self.resolve()
            path.write_bytes(original)

    def test_rehashed_metadata_and_compiled_bytes_cannot_change_producer_checkpoint(self):
        path = self.manifest(); original = json.loads(path.read_bytes())
        for role in ('metadata', 'compiled', 'bundle'):
            value = deepcopy(original); row = next(x for x in value['files'] if x['role'] == role)
            artifact = self.directory / row['file']; before = artifact.read_bytes(); changed = before + b'changed'
            artifact.write_bytes(changed); row.update(bytes=len(changed), sha256=subject.digest(changed))
            path.write_bytes(subject.canonical(value))
            with self.subTest(role=role), self.assertRaisesRegex(ValueError, 'producer closure'):
                self.resolve()
            artifact.write_bytes(before)

    def test_rehashed_export_cannot_claim_a_new_native_observation(self):
        path = self.exports['crew']; value = json.loads(path.read_bytes()); value['data']['version'] = True
        raw = subject.canonical(value); path.write_bytes(raw)
        manifest = json.loads(self.manifest().read_bytes()); manifest['export'].update(bytes=len(raw), sha256=subject.digest(raw))
        self.manifest().write_bytes(subject.canonical(manifest))
        with self.assertRaisesRegex(ValueError, 'unaccepted historical export'):
            self.resolve()

    def test_duplicate_noncanonical_and_oversized_manifest_rejected(self):
        path = self.manifest(); raw = path.read_bytes()
        for changed in (raw.replace(b'"version": 1', b'"version": 1, "version": 1', 1),
                        raw.replace(b'\n', b'\r\n'), b' ' * 16385):
            path.write_bytes(changed)
            with self.subTest(length=len(changed)), self.assertRaises(ValueError):
                self.resolve()

    def test_real_directory_junction_is_rejected(self):
        import _winapi
        path = self.directory / (self.exports['crew'].stem + '.relocated')
        target = self.directory / 'junction-target'; path.rename(target)
        _winapi.CreateJunction(str(target), str(path))
        try:
            with self.assertRaisesRegex(ValueError, 'linked evidence'):
                self.resolve()
        finally:
            path.rmdir()
            target.rename(path)

    def test_resolution_refuses_unmapped_proof_or_trace_root(self):
        resolver = self.resolve()
        with self.assertRaisesRegex(ValueError, 'unmapped'):
            resolver.proof_path('trace', str(self.directory / 'other.jsonl'))
        with self.assertRaisesRegex(ValueError, 'trace root'):
            resolver.trace_root(str(self.directory))

    def test_import_refuses_unaccepted_export_before_writing(self):
        source = self.directory / 'unknown.json'; source.write_bytes(subject.canonical({'kind': 'native-ms1-crew'}))
        target = self.directory / 'new' / 'export.json'
        with self.assertRaisesRegex(ValueError, 'unaccepted'):
            subject.import_export(source, self.directory, target)
        self.assertFalse(target.parent.exists())

    def test_current_generator_identity_is_actual_bytes_and_historical_record_is_explicit(self):
        actual = crew.dependencies()
        self.assertEqual(actual['sha256'], hashlib.sha256(Path(crew.__file__).read_bytes()).hexdigest())
        self.assertNotEqual(actual['sha256'], crew.HISTORICAL_GENERATOR_SHA)
        historical = {k: v for k, v in actual.items() if k != 'evidence_relocation'}
        historical['sha256'] = crew.HISTORICAL_GENERATOR_SHA
        self.assertEqual(crew.validate_generator_provenance(historical), historical)
        self.assertEqual(crew.validate_generator_provenance(actual), actual)
        for mutation in (lambda x: x.update(sha256='0' * 64),
                         lambda x: x['dependency'].update(sha256='0' * 64),
                         lambda x: x.update(evidence_relocation={'version': 999})):
            changed = deepcopy(historical); mutation(changed)
            with self.assertRaises(ValueError):
                crew.validate_generator_provenance(changed)


if __name__ == '__main__':
    unittest.main()
