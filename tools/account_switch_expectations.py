"""Read-only expectations for the two frozen accounts in the S acceptance card.

This is deliberately not a game-state generator or a general account loader.
The accepted pre-card manifests anchor the inputs; independent literal/delta
checks then bind the native snapshot to their actual payloads. No credential,
database, native client or generator is loaded or executed here.
"""
import argparse
import math
from pathlib import Path
import re
import unicodedata

import verify_ms1_crew_native as crew
import verify_hangar_ui as ui
import verify_unified_entry as entry
from client_audit import ROOT, config, output_dir, read_limited, save_json
from verify_hangar import digest, literal, local_file, require, same_literal

VERSION = 1
PAYLOADS = ('state.bin', 'shop.bin', 'dossier.bin')
PRIMARY = 'c5326cc1-8524-479c-8bba-72e973489c22'
SECONDARY = '271022a3-41e0-406e-b6fa-59930c320442'
PINS = {
    PRIMARY: ('c979a7dafe36ec0130c0c472ccfdda328300e12f8d3ecdadde1881a6435ff685',
              '5167ea63f0503952b4ab1e7c4b1ed2dca5e5da6b6812bd476a87124a891e0888'),
    SECONDARY: ('7de4ade1c324f05ee91929c5eb030684058fa9a4bac03e72c8beef75c34aafb7',
                'b8de0e18d174178815eae3db4acb28a91a3f5c5eddc60aa43e668b6e3b2d6b13'),
}
ANCHOR = ('evidence/20261005-p02-inprocess-relogin/final-audit-01/final-state-audit.json',
          '0ff1f08a1c7d56a3ac1c1e378aa4848d74511ead31bad52745df6916ffc6ff35')
LEGACY_MANIFEST_SHA = 'ca1e260fb2c45dd932c83869c16b0ed72270676b4cdef433c6b2f5ca4b5a4d56'
NATIVE_MS1_SHA = '18e6c2babfc205ce80fa24c2c9f23385a1731233c4d504be369638485652d6f2'
MAX_I32 = 2147483647
VEHICLES = {3329: (90, 2), 7169: (2150, 5)}


def same(actual, wanted, message):
    require(same_literal(actual, wanted), message)


def integer(value, minimum=0, maximum=MAX_I32):
    require(type(value) is int and minimum <= value <= maximum, 'bounded integer required')
    return value


def json_file(directory, name, maximum=65536):
    raw = local_file(directory, name, maximum)
    value = entry.json_data(raw)
    pending, nodes = [(value, 0)], 0
    while pending:
        item, depth = pending.pop()
        nodes += 1
        require(nodes <= 16384 and depth <= 16, 'JSON depth/node bound')
        if type(item) is dict:
            pending.extend((child, depth + 1) for child in item.values())
        elif type(item) is list:
            pending.extend((child, depth + 1) for child in item)
        else:
            require(type(item) in (str, int, bool, float, type(None)), 'JSON primitive type')
            require(type(item) is not float or math.isfinite(item), 'JSON nonfinite number')
    require(type(value) is dict, 'JSON object required')
    return value, raw


def anchor_inputs(directory, account):
    require(account in PINS, 'account outside the frozen two-account card')
    manifest, raw = json_file(directory, 'manifest.json')
    profile, profile_raw = json_file(directory, 'profile-input.json')
    require(digest(raw) == PINS[account][0] and digest(profile_raw) == PINS[account][1],
            'fixture changed since the accepted pre-card audit')
    same(manifest['account_id'], account, 'manifest account identity')
    same(profile['account_id'], account, 'profile account identity')
    return manifest, raw, profile, profile_raw


def payloads(directory, manifest):
    rows = manifest.get('files')
    require(type(rows) is list and len(rows) == 3
            and [r.get('file') for r in rows] == list(PAYLOADS), 'payload manifest schema/order')
    result = {}
    for row in rows:
        name = row['file']
        raw = local_file(directory, name, entry.MAX_RAW)
        require(integer(row['bytes'], 4, entry.MAX_RAW) == len(raw)
                and digest(raw) == row['sha256'], 'payload hash or size differs')
        literal(raw)
        result[name] = raw
    return result


def profile_identity(profile, manifest, compatibility):
    database_id = integer(profile['native_database_id'], 1)
    same(manifest['native_database_id'], database_id, 'manifest native identity')
    same(compatibility['native_database_id'], database_id, 'compatibility native identity')
    same(compatibility['account_id'], profile['account_id'], 'compatibility account identity')
    name = profile['username']
    require(type(name) is str and re.fullmatch(r'[A-Za-zА-Яа-яЁё0-9_]{3,24}', name)
            and unicodedata.normalize('NFC', name) == name and len(name.encode('utf8')) <= 48,
            'nickname outside the measured contract')
    same(compatibility['client_name'], name, 'compatibility public nickname')
    return database_id, name


def load_secondary_fixture(directory, local_root):
    """Verify the unchanged r1 plus the five native mounted catalogue entries."""
    manifest, manifest_raw, profile, profile_raw = anchor_inputs(directory, SECONDARY)
    require(set(profile) == {'profile_version', 'account_id', 'username', 'native_database_id',
            'created_at_ms', 'snapshot_revision', 'resources', 'statistics'}, 'legacy profile1 schema')
    same(profile['profile_version'], 1, 'legacy profile version')
    same(profile['snapshot_revision'], 1, 'legacy snapshot version')
    integer(profile['created_at_ms'], 1000000000000, 4102444800000)
    same(manifest['fixture_version'], 1, 'legacy fixture version')
    same(manifest['compatibility_catalog_revision'], 2, 'legacy catalogue revision')
    require(manifest['ruleset'] == 'test_lab' and manifest['vehicle_available'] is True,
            'legacy fixture scope')
    same(manifest['profile_source'], {'file': 'profile-input.json', 'relative_to': 'fixture_directory',
          'sha256': digest(profile_raw)}, 'legacy profile source')
    migration, migration_raw = json_file(directory, 'catalog-migration.json')
    require(set(migration) == {'version', 'catalog_revision', 'previous'},
            'catalogue migration schema')
    same(migration['version'], 1, 'migration version')
    same(migration['catalog_revision'], 2, 'migration catalogue version')
    previous = migration['previous']
    require(type(previous) is dict and set(previous) == {'directory', 'manifest_sha256', 'files', 'profile_sha256'}
            and previous['directory'] == 'r1' and previous['manifest_sha256'] == LEGACY_MANIFEST_SHA,
            'immutable r1 migration source')
    baseline = entry.owned(directory.parent / 'r1', local_root, directory=True)
    old_manifest, old_manifest_raw = json_file(baseline, 'manifest.json')
    require(digest(old_manifest_raw) == LEGACY_MANIFEST_SHA, 'historical r1 manifest hash')
    require(len(manifest) == 16 and set(manifest) == set(old_manifest) | {'compatibility_catalog_revision'},
            'catalogue manifest schema')
    changing = {'files', 'generator', 'native_descriptors', 'compatibility_catalog_revision'}
    for key in set(old_manifest) - changing:
        same(manifest[key], old_manifest[key], 'catalogue changed domain metadata')
    require(manifest['generator']['sha256'] == ui.CATALOG_GENERATOR_SHA, 'catalogue generator identity')
    same(profile_raw, local_file(baseline, 'profile-input.json', 65536), 'catalogue changed profile bytes')
    require(previous['profile_sha256'] == digest(profile_raw), 'migration profile hash')
    compatibility, _ = json_file(directory, 'compatibility.json')
    old_compatibility, _ = json_file(baseline, 'compatibility.json')
    wanted_compatibility = dict(old_compatibility, compatibility_catalog_revision=2)
    same(compatibility, wanted_compatibility, 'catalogue changed compatibility identity')
    native_id, name = profile_identity(profile, manifest, compatibility)
    old_raw, raw = payloads(baseline, old_manifest), payloads(directory, manifest)
    same(previous['files'], {k: digest(v) for k, v in old_raw.items()}, 'migration old payload hashes')
    for filename in ('state.bin', 'dossier.bin'):
        same(raw[filename], old_raw[filename], 'catalogue changed player state/dossier bytes')
    source, old_source = manifest['native_descriptors'], old_manifest['native_descriptors']
    require(set(source) == set(old_source) | {'mounted_module_price_sources'}, 'mounted source schema')
    for key in old_source:
        same(source[key], old_source[key], 'catalogue changed native descriptor provenance')
    native_path = entry.owned(source['file'], local_root)
    native_raw = read_limited(native_path, entry.MAX_RAW)
    require(digest(native_raw) == source['sha256'] == NATIVE_MS1_SHA
            and integer(source['bytes'], 1, entry.MAX_RAW) == len(native_raw), 'native MS1 source hash/size')
    native = entry.json_data(native_raw)
    prices, native_proof = ui.mounted_catalog_sources(source, native)
    ui.catalog_shop_delta(literal(old_raw['shop.bin']), literal(raw['shop.bin']), prices)
    state = literal(raw['state.bin'])
    same(state[b'rev'], 1, 'native state revision')
    same(literal(raw['dossier.bin']), (0, []), 'legacy native vehicle dossier cursor')
    same(state[b'inventory'][1][b'compDescr'], {1: bytes.fromhex(native['vehicle']['compact_descr_hex'])},
         'secondary garage differs from native MS1 descriptor')
    same(state[b'inventory'][1][b'crew'], {1: [None, None]}, 'secondary crew assignment changed')
    same(state[b'inventory'][8], {b'compDescr': {}}, 'secondary has foreign tankmen')
    require(type(state[b'intUserSettings']) is dict and 54 not in state[b'intUserSettings'],
            'legacy license consent fabricated')
    entry.validate_registered_dossier(bytes.fromhex(native['account_dossier_hex']),
                                      state[b'stats'][b'dossier'], profile['created_at_ms'])
    same(profile['statistics'], manifest['statistics'], 'legacy statistics differ')
    expected = {'raw': raw, 'manifest': manifest, 'manifest_sha256': digest(manifest_raw),
                'profile': profile, 'profile_sha256': digest(profile_raw), 'account_id': SECONDARY,
                'native_id': native_id, 'name': name, 'state': state, 'resources': profile['resources'],
                'dossier_cache': None, 'fixture': str(directory)}
    return expected, {'status': 'PASS', 'fixture': str(directory), 'manifest_sha256': digest(manifest_raw),
        'profile_sha256': digest(profile_raw), 'baseline_manifest_sha256': digest(old_manifest_raw),
        'migration_sha256': digest(migration_raw), 'native_resource_provenance': native_proof,
        'profile_state_and_dossier_byte_identical_to_r1': True, 'catalogue_revision': 2,
        'native_compatibility': 'NOT_RUN by this read-only helper; current native rendering is a separate gate'}


def snapshot(expected, compatibility):
    """Project exact native-observable fields; reject dangling/bool/foreign IDs."""
    profile, state = expected['profile'], expected['state']
    database_id, name = profile_identity(profile, expected['manifest'], compatibility)
    stats = state[b'stats']
    resources = {public: integer(stats[wire]) for public, wire in (
        ('credits', b'credits'), ('gold', b'gold'), ('free_xp', b'freeXP'))}
    same(resources, profile['resources'], 'native resources differ from domain profile')
    statistics = profile['statistics']
    same(statistics, {'battles': 0, 'wins': 0, 'losses': 0, 'draws': 0}, 'unmeasured battle statistics')
    dossier = stats[b'dossier']
    require(type(dossier) is bytes and len(dossier) == 88, 'native account dossier bytes')
    inventory = state[b'inventory']
    require(type(inventory) is dict and set(inventory) == {1, 8}, 'unmeasured inventory categories')
    vehicle_data, tankman_data = inventory[1], inventory[8]
    require(type(vehicle_data) is dict and type(tankman_data) is dict, 'inventory field maps')
    compacts, tankman_compacts = vehicle_data[b'compDescr'], tankman_data[b'compDescr']
    require(type(compacts) is dict and 1 <= len(compacts) <= 8
            and type(tankman_compacts) is dict and len(tankman_compacts) <= 16, 'fleet/crew size bound')
    for row in (compacts, tankman_compacts):
        for identifier in row:
            integer(identifier, 1)
    mappings = compatibility['vehicle_mapping']
    require(type(mappings) is list and len(mappings) == len(compacts), 'vehicle mapping count')
    mapped = {}
    for row in mappings:
        identifier = integer(row['native_inventory_id'], 1)
        require(identifier not in mapped and identifier in compacts, 'duplicate/foreign vehicle mapping')
        mapped[identifier] = integer(row['type_compact_descr'], 1, 65535)
    for key in (b'crew', b'repair'):
        require(type(vehicle_data[key]) is dict, 'vehicle column map required')
        same(sorted(vehicle_data[key]), sorted(compacts), 'vehicle column inventory IDs differ')
    assigned, vehicles = {}, []
    for identifier, compact in sorted(compacts.items()):
        require(type(compact) is bytes and len(compact) == 15 and compact[0] == 1 and compact[-1] == 0,
                'unmeasured mounted vehicle compact shape')
        type_cd = compact[1] * 256 + compact[0]
        same(type_cd, mapped[identifier], 'native compact/mapping type differs')
        require(type_cd in VEHICLES, 'unmeasured native vehicle type')
        max_health, slots = VEHICLES[type_cd]
        repair, crew_ids = vehicle_data[b'repair'][identifier], vehicle_data[b'crew'][identifier]
        require(type(repair) is tuple and len(repair) == 2, 'native repair tuple')
        integer(repair[0])
        health = integer(repair[1], 0, max_health)
        require(type(crew_ids) is list and len(crew_ids) == slots, 'native crew seat count/type')
        for seat, tankman in enumerate(crew_ids):
            if tankman is None:
                continue
            integer(tankman, 1)
            require(tankman in tankman_compacts and tankman not in assigned, 'dangling/duplicate crew assignment')
            assigned[tankman] = (identifier, seat)
        vehicles.append({'inventory_id': identifier, 'type_compact_descr': type_cd,
            'compact_descr_sha256': digest(compact), 'health': health, 'crew_ids': list(crew_ids)})
    owners = tankman_data.get(b'vehicle', {})
    require(type(owners) is dict, 'native tankman owner map')
    same(sorted(owners), sorted(tankman_compacts), 'native tankman owner keys differ')
    same(sorted(assigned), sorted(tankman_compacts), 'unmeasured unassigned tankman')
    tankmen = []
    for identifier, compact in sorted(tankman_compacts.items()):
        require(type(compact) is bytes and len(compact) == 25, 'native tankman compact shape')
        vehicle, seat = assigned[identifier]
        same(owners[identifier], vehicle, 'crew forward/reverse assignment differs')
        tankmen.append({'inventory_id': identifier, 'compact_descr_sha256': digest(compact),
                        'vehicle_inventory_id': vehicle, 'vehicle_slot_index': seat})
    return {'database_id': database_id, 'name': name, 'resources': resources,
            'statistics': dict(statistics), 'account_dossier_sha256': digest(dossier),
            'vehicles': vehicles, 'tankmen': tankmen}


def load_pair(primary_fixture, secondary_fixture, native_export, local_root):
    local_root = Path(local_root).resolve(strict=True)
    primary_fixture = entry.owned(primary_fixture, local_root, directory=True)
    secondary_fixture = entry.owned(secondary_fixture, local_root, directory=True)
    native_export = entry.owned(native_export, local_root)
    anchor_raw = local_file(local_root, ANCHOR[0], 2 * 1024 * 1024)
    require(digest(anchor_raw) == ANCHOR[1] and entry.json_data(anchor_raw)['status'] == 'PASS',
            'accepted pre-card fixture anchor differs')
    anchor_inputs(primary_fixture, PRIMARY)
    export, export_proof = crew.export_evidence(native_export, local_root)
    primary, primary_proof = crew.crew_fixture(primary_fixture, export, export_proof, local_root)
    secondary, secondary_proof = load_secondary_fixture(secondary_fixture, local_root)
    expected = [primary, secondary]
    accounts = [snapshot(item, json_file(Path(item['fixture']), 'compatibility.json')[0]) for item in expected]
    require(primary['account_id'] != secondary['account_id'] and accounts[0]['database_id'] != accounts[1]['database_id']
            and accounts[0]['name'] != accounts[1]['name']
            and accounts[0]['account_dossier_sha256'] != accounts[1]['account_dossier_sha256'],
            'accounts lack distinct measured identity/dossier')
    same([len(a['vehicles']) for a in accounts], [2, 1], 'two-account fleet discriminator')
    same([len(a['tankmen']) for a in accounts], [2, 0], 'two-account crew discriminator')
    proof = {'status': 'PASS', 'version': VERSION, 'phase_accounts': [0, 1, 0],
             'anchor': {'file': str(local_root / ANCHOR[0]), 'sha256': ANCHOR[1]},
             'accounts': [primary_proof, secondary_proof], 'native_export': export_proof,
             'payloads': [{name: {'bytes': len(raw), 'sha256': digest(raw)} for name, raw in item['raw'].items()}
                          for item in expected],
             'credentials_read': False, 'database_read': False, 'game_state_written': False,
             'scope': 'Frozen expected inputs only; no authentication, native account switch or rendering claim'}
    return {'expected': expected, 'expected_accounts': accounts, 'provenance': proof}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--primary-fixture', required=True)
    parser.add_argument('--secondary-fixture', required=True)
    parser.add_argument('--native-export', required=True)
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    result = load_pair(args.primary_fixture, args.secondary_fixture, args.native_export,
                       config()[1]['local_artifacts_root'])
    out = output_dir(args.out)
    save_json(out / 'expected-accounts.json', result['expected_accounts'])
    save_json(out / 'expectations-proof.json', result['provenance'])
    print('PASS: two frozen account expectations; native switch NOT_RUN')


if __name__ == '__main__':
    main()
