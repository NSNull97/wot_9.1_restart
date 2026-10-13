"""Test-only regeneration of the exact accepted r2/r3 payloads at new paths.

Archived manifests are never rewritten. New manifests name the actual current
generators; six output streams and all domain inputs must equal the archives.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import native_evidence_relocation as evidence
import test_garage_state as garage
import ms1_crew_state as crew

ACCOUNT = 'c5326cc1-8524-479c-8bba-72e973489c22'
ARCHIVE = ROOT / 'local/server/fixtures' / ACCOUNT
MANIFESTS = {2: '3de57cf5719c8159a5a5dd7c96080168b15cde3fe2ecf76dd2c29993ad32ba21',
             3: 'c979a7dafe36ec0130c0c472ccfdda328300e12f8d3ecdadde1881a6435ff685'}
PAYLOADS = ('state.bin', 'shop.bin', 'dossier.bin')
INPUTS = ('profile-input.json', 'base-profile-input.json')


def archive(root):
    root = evidence.local(root)
    result = {}
    for revision, expected in MANIFESTS.items():
        directory = root / f'r{revision}-catalog3'
        raw = evidence.read(directory / 'manifest.json', 65536)
        evidence.require(evidence.digest(raw) == expected, 'unaccepted archived fixture manifest')
        manifest = evidence.parse(raw)
        for field, name in [('profile_source', INPUTS[0]), ('base_profile_source', INPUTS[1])]:
            content = evidence.read(directory / name, 8192)
            evidence.require(manifest[field] == {'file': name, 'relative_to': 'fixture_directory',
                'sha256': evidence.digest(content)}, 'archived profile bytes changed')
        for name in PAYLOADS:
            rows = [row for row in manifest['files'] if row['file'] == name]
            content = evidence.read(directory / name, 16384)
            evidence.require(len(rows) == 1 and rows[0]['bytes'] == len(content)
                    and rows[0]['sha256'] == evidence.digest(content), 'archived payload bytes changed')
        result[revision] = directory
    evidence.require((result[3] / INPUTS[1]).read_bytes() == (result[2] / INPUTS[0]).read_bytes(),
                     'archived profile chain changed')
    return result


def compare(source, target):
    records = []
    for revision in (2, 3):
        old = source[revision]; new = target / f'r{revision}-catalog3'
        for name in PAYLOADS + INPUTS:
            original = evidence.read(old / name, 16384); current = evidence.read(new / name, 16384)
            evidence.require(current == original, 'regeneration changed accepted bytes: ' + name)
            records.append({'revision': revision, 'file': name, 'bytes': len(original),
                            'sha256': evidence.digest(original), 'equal': True})
    return records


def migrate(source, target):
    original = archive(source); target = evidence.local(target)
    evidence.require(not target.exists(), 'test fixture migration is append-only')
    target.mkdir(parents=True)
    ms1 = ROOT / 'local/evidence/20261004-p02-hangar/native-descriptors.json'
    is7 = ROOT / 'local/evidence/20261004-p02-hangar-ui/ui06-catalog2-manual-runtime/original-vehicle-is7.json'
    export = ROOT / 'local/evidence/20261005-p02-ms1-crew/native-ms1-crew-export01.json'
    garage.generate(original[2] / INPUTS[0], original[2] / INPUTS[1], ms1, is7, target / 'r2-catalog3')
    crew.generate(original[3] / INPUTS[0], target / 'r2-catalog3', export, target / 'r3-catalog3')
    records = compare(original, target)
    receipt = {'version': 1, 'kind': 'test-native-fixture-migration', 'source': str(evidence.local(source)),
               'archive_manifests': {str(k): v for k, v in MANIFESTS.items()}, 'output': str(target),
               'records': records, 'generated_manifests': {str(revision): evidence.digest(evidence.read(
                   target / f'r{revision}-catalog3/manifest.json', 65536)) for revision in (2, 3)},
               'native_acceptance': 'NOT_RUN; exact archival payload regeneration only'}
    (target / 'migration-receipt.json').write_bytes(evidence.canonical(receipt))
    return receipt


def fixture(revision):
    """An explicit env override is verified, never silently falls back."""
    configured = os.environ.get('MS1_TEST_FIXTURE_ROOT')
    if configured is None:
        return ARCHIVE / f'r{revision}-catalog3'
    root = evidence.local((ROOT / configured).absolute())
    receipt = evidence.parse(evidence.read(root / 'migration-receipt.json', 16384))
    evidence.require(set(receipt) == {'version', 'kind', 'source', 'archive_manifests', 'output', 'records',
        'generated_manifests', 'native_acceptance'} and type(receipt['version']) is int and receipt['version'] == 1
        and receipt['kind'] == 'test-native-fixture-migration' and receipt['output'] == str(root)
        and receipt['archive_manifests'] == {str(k): v for k, v in MANIFESTS.items()}, 'fixture migration receipt mismatch')
    original = archive(receipt['source'])
    evidence.require(receipt['records'] == compare(original, root), 'fixture migration payload receipt changed')
    for version in (2, 3):
        evidence.require(receipt['generated_manifests'][str(version)] == evidence.digest(evidence.read(
            root / f'r{version}-catalog3/manifest.json', 65536)), 'regenerated manifest changed')
    return root / f'r{revision}-catalog3'


def proof_paths(export_path):
    """Use the explicit resolver in low-level producer mutation tests too."""
    raw = evidence.read(export_path, 32768); value = evidence.parse(raw)
    relocated = evidence.for_export(export_path, raw)
    return {role: relocated.proof_path(role, value['source'][role + '_file']) if relocated
            else evidence.local(value['source'][role + '_file'])
            for role in ('trace', 'install_plan', 'outcome')}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, default=ARCHIVE)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(migrate(args.archive, args.out), indent=2))
