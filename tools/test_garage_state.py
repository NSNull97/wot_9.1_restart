"""Explicit offline test-grant snapshots; no database writes or client execution.

Profile2 adds the owner-requested IS-7 to one existing zero-battle profile. Domain
snapshot2 is independent of native per-session Account sync revision1. Native
descriptors and reference prices come only from the configured original client
and actual local constructor evidence. The historical encoder stays unchanged.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import pickletools
import re
import struct
import uuid

import hangar_state as legacy
from client_audit import ROOT, config, read_limited, save_json, sha256
from packed_xml import decode, walk


PROFILE_VERSION = 2
SNAPSHOT_REVISION = 2
CATALOG_REVISION = 3
WIRE_SYNC_REVISION = 1
DOSSIER_CACHE_VERSION = 1
GRANT_ID = 'test-is7-v1'
ENCODER_SHA256 = 'ac60b6ea2be39eaa59327ef1eefb935595e8111ff13a12720ed3a3ebf02c7e79'
PROFILE_FIELDS = {'profile_version', 'account_id', 'username', 'native_database_id',
                  'created_at_ms', 'snapshot_revision', 'resources', 'statistics'}
INVENTORY_FIELDS = {'inventory_id', 'vehicle_definition_id', 'health', 'vehicle_xp',
                    'crew_assigned', 'ammunition_count'}
COMPONENTS = ('chassis', 'engine', 'fuelTank', 'radio', 'turret', 'gun')
COMPONENT_KINDS = dict(zip(COMPONENTS, (2, 5, 6, 7, 3, 4)))
VISIBLE_COMPONENTS = ('chassis', 'turret', 'gun', 'engine', 'radio')


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def bounded_int(value, label, minimum=0, maximum=(1 << 31) - 1):
    return legacy.bounded_int(value, label, minimum, maximum)


def verify_encoder():
    path = Path(legacy.__file__).resolve()
    if sha256(path) != ENCODER_SHA256:
        raise ValueError('frozen hangar encoder changed; explicit migration required')
    return {'file': str(path), 'sha256': ENCODER_SHA256}


def local_file(path, exists=True):
    _, paths = config()
    result = Path(path).resolve(strict=exists)
    if not result.is_relative_to(paths['local_artifacts_root']) or result == paths['local_artifacts_root']:
        raise ValueError('test garage inputs/outputs must remain below local/')
    return result


def bounded_json(raw, maximum=8192):
    if type(raw) is not bytes or len(raw) > maximum:
        raise ValueError('bounded JSON bytes required')

    def object_pairs(pairs):
        result = {}
        if len(pairs) > 32:
            raise ValueError('JSON object field bound')
        for key, value in pairs:
            if key in result:
                raise ValueError('duplicate JSON field')
            result[key] = value
        return result

    try:
        value = json.loads(raw.decode('utf8'), object_pairs_hook=object_pairs,
                           parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite JSON number')))
    except (RecursionError, UnicodeError) as error:
        raise ValueError('invalid bounded UTF8 JSON') from error
    nodes = 0

    def visit(item, depth):
        nonlocal nodes
        nodes += 1
        if nodes > 512 or depth > 8:
            raise ValueError('JSON structural bound')
        if type(item) is dict:
            for child in item.values():
                visit(child, depth + 1)
        elif type(item) is list:
            if len(item) > 32:
                raise ValueError('JSON array bound')
            for child in item:
                visit(child, depth + 1)
        elif type(item) is str and len(item) > 8192:
            raise ValueError('JSON scalar bound')
    visit(value, 0)
    return value


def validate_base_profile(value):
    if type(value) is not dict or set(value) != PROFILE_FIELDS:
        raise ValueError('exact profile1 fields required')
    if type(value['profile_version']) is not int or value['profile_version'] != 1:
        raise ValueError('profile1 required')
    if type(value['snapshot_revision']) is not int or value['snapshot_revision'] != 1:
        raise ValueError('domain snapshot1 required')
    account_id = value['account_id']
    if type(account_id) is not str or str(uuid.UUID(account_id)) != account_id:
        raise ValueError('canonical account UUID required')
    nickname = value['username']
    if (type(nickname) is not str or not re.fullmatch(r'[A-Za-zА-Яа-яЁё0-9_]{3,24}', nickname)
            or len(nickname.encode('utf8')) > 48):
        raise ValueError('stored Russian/Latin nickname required')
    bounded_int(value['native_database_id'], 'native account ID', 1)
    bounded_int(value['created_at_ms'], 'registration timestamp', 1, 4000000000000)
    resources = value['resources']
    if type(resources) is not dict or set(resources) != {'credits', 'gold', 'free_xp'}:
        raise ValueError('exact resource fields required')
    for item in resources.values():
        bounded_int(item, 'resource balance')
    stats = value['statistics']
    if type(stats) is not dict or set(stats) != {'battles', 'wins', 'losses', 'draws'}:
        raise ValueError('exact new-account statistics required')
    if any(type(x) is not int or x != 0 for x in stats.values()):
        raise ValueError('this test grant supports only zero-battle profiles')
    return value


def read_base_profile(path):
    path = local_file(path)
    raw = read_limited(path, 8192)
    return validate_base_profile(bounded_json(raw)), {'file': str(path), 'sha256': digest(raw)}, raw


def expected_inventory(account_id):
    return [dict(inventory_id=account_id + ':starter-vehicle-v1', vehicle_definition_id='vehicle:ms1',
                 health=90, vehicle_xp=0, crew_assigned=False, ammunition_count=0),
            dict(inventory_id=account_id + ':' + GRANT_ID, vehicle_definition_id='vehicle:is7',
                 health=2150, vehicle_xp=0, crew_assigned=False, ammunition_count=0)]


def promote_profile(base, base_profile_sha256, granted_at_ms):
    """Deterministic proposal only. Persistence/idempotent ledger belong to caller."""
    validate_base_profile(base)
    if type(base_profile_sha256) is not str or not re.fullmatch('[0-9a-f]{64}', base_profile_sha256):
        raise ValueError('exact source profile SHA256 required')
    bounded_int(granted_at_ms, 'explicit grant timestamp', base['created_at_ms'], 2147483647999)
    result = deepcopy(base)
    result.update(profile_version=PROFILE_VERSION, snapshot_revision=SNAPSHOT_REVISION,
                  inventory=expected_inventory(base['account_id']),
                  test_grant={'grant_id': GRANT_ID, 'granted_at_ms': granted_at_ms,
                              'base_profile_sha256': base_profile_sha256})
    return result


def validate_profile(value, base, base_profile_sha256):
    if type(value) is not dict or set(value) != PROFILE_FIELDS | {'inventory', 'test_grant'}:
        raise ValueError('exact profile2 fields required')
    if type(value['profile_version']) is not int or value['profile_version'] != PROFILE_VERSION:
        raise ValueError('profile2 required')
    if type(value['snapshot_revision']) is not int or value['snapshot_revision'] != SNAPSHOT_REVISION:
        raise ValueError('domain snapshot2 required')
    grant = value['test_grant']
    if type(grant) is not dict or set(grant) != {'grant_id', 'granted_at_ms', 'base_profile_sha256'}:
        raise ValueError('exact explicit grant provenance required')
    expected = promote_profile(base, base_profile_sha256, grant['granted_at_ms'])
    inventory = value['inventory']
    if type(inventory) is not list or len(inventory) != 2:
        raise ValueError('exactly two granted inventory entries required')
    for item in inventory:
        if type(item) is not dict or set(item) != INVENTORY_FIELDS:
            raise ValueError('exact inventory entry fields required')
        for field in ('health', 'vehicle_xp', 'ammunition_count'):
            bounded_int(item[field], field)
        if type(item['crew_assigned']) is not bool:
            raise ValueError('explicit crew assignment boolean required')
    # Type-sensitive validation prevents True==1 from satisfying preservation.
    current_base = {key: value[key] for key in PROFILE_FIELDS}
    current_base.update(profile_version=1, snapshot_revision=1)
    validate_base_profile(current_base)
    if value != expected:
        raise ValueError('profile2 differs from exact authorized test grant or base profile')
    return value


def integral_reference_price(value):
    if type(value) is int:
        return bounded_int(value, 'reference price')
    # Original IS-7 chassis/turret use integral decimal strings 82500.0/66000.0.
    # Avoid binary float rounding, exponents, signs, fractions or coercing bool.
    if type(value) is not str or len(value) > 24 or not re.fullmatch(r'(0|[1-9][0-9]*)(?:\.0+)?', value):
        raise ValueError('nonintegral original resource reference price')
    return bounded_int(int(value.split('.')[0]), 'reference price')


def is7_reference_prices(native, client_root):
    cache = {}

    def resource(name):
        if name not in cache:
            path = client_root / 'res/scripts/item_defs/vehicles/ussr' / name
            raw = read_limited(path, 2 * 1024 * 1024)
            cache[name] = (dict(walk(decode(raw))), {'file': str(path), 'sha256': digest(raw)})
        return cache[name]

    vehicle, vehicle_source = resource('is-7.xml')
    definitions = (
        ('chassis', 'IS-7', 'chassis.xml', '/chassis[1]/IS-7[1]'),
        ('engine', 'M-50T', 'engines.xml', '/engines[1]/M-50T[1]'),
        ('fuelTank', 'Large', 'fuelTanks.xml', '/fuelTanks[1]/Large[1]'),
        ('radio', '_10RK-26', 'radios.xml', '/radios[1]/_10RK-26[1]'),
        ('turret', 'IS-7', 'turrets.xml', '/turrets0[1]/IS-7[1]'),
        ('gun', '_130mm_S-70', 'guns.xml', '/turrets0[1]/IS-7[1]/guns[1]/_130mm_S-70[1]'),
    )
    compact = legacy.bounded_hex(native['compact_descr_hex'], 'IS-7 descriptor', 15)
    if len(compact) != 15:
        raise ValueError('original default IS-7 descriptor length')
    fields = struct.unpack('<2B6HB', compact)
    if fields[:2] != (1, 28) or fields[-1] != 0 or native['type_compact_descr'] != 7169:
        raise ValueError('IS-7 native descriptor header/type/flags mismatch')
    if set(native['components']) != set(COMPONENTS):
        raise ValueError('six native mounted component IDs required')
    if (native['max_health'] != vehicle['/hull[1]/maxHealth[1]'] + vehicle['/turrets0[1]/IS-7[1]/maxHealth[1]']
            or native['max_health'] != 2150 or native['crew_roles'] != [
                ['commander'], ['gunner'], ['driver'], ['loader'], ['loader', 'radioman']]):
        raise ValueError('IS-7 HP/roles differ from measured native/resources')
    prices, evidence = {}, []
    for index, (kind, name, filename, node) in enumerate(definitions):
        values, source = resource('components/' + filename)
        id_node = '/ids[1]/' + name + '[1]'
        local_id = bounded_int(values[id_node], 'original component ID', 0, 65535)
        expected_cd = (local_id << 8) + COMPONENT_KINDS[kind]
        if fields[index + 2] != local_id or native['components'][kind] != expected_cd:
            raise ValueError('native component differs from original resource ID/descriptor bytes')
        if node not in vehicle:
            raise ValueError('mounted component is not in original IS-7 base configuration')
        if kind not in VISIBLE_COMPONENTS:
            continue
        shared = vehicle[node] == 'shared'
        price_values, price_source = (values, source) if shared else (vehicle, vehicle_source)
        price_node = ('/shared[1]/' + name + '[1]' if shared else node) + '/price[1]'
        original_value = price_values[price_node]
        amount = integral_reference_price(original_value)
        gold = price_node + '/gold[1]' in price_values
        prices[expected_cd] = (0, amount) if gold else (amount, 0)
        evidence.append({'component': kind, 'compact_descr': expected_cd,
                         'id_source': dict(source, node=id_node, source_value=local_id),
                         'price_source': dict(price_source, node=price_node, raw_value=original_value,
                                              integral_value=amount, gold_child_present=gold),
                         'classification': 'original reference value only; purchases/install/sale unavailable'})
    return prices, evidence


def grant_vehicle_dossier(original, granted_at_ms):
    """Change only creationTime in the measured native empty vehicle dossier."""
    if type(original) is not bytes or len(original) != 70:
        raise ValueError('unrecognized empty vehicle dossier length')
    header = struct.unpack_from('<26H', original)
    sizes = header[1:]
    if header[0] != 81 or sizes[9] != 18 or sum(sizes) != 18 or any(original[56:]):
        raise ValueError('vehicle dossier is not the original zero-battle layout')
    seconds = bounded_int(granted_at_ms // 1000, 'grant seconds', 1)
    return original[:52] + struct.pack('<I', seconds) + original[56:]


def read_native_inputs(ms1_path, is7_path):
    verify_encoder()
    ms1, ms1_source = legacy.descriptors(local_file(ms1_path), catalog_version=2)
    is7_path = local_file(is7_path)
    raw = read_limited(is7_path, 32768)
    original = bounded_json(raw, 32768)
    is7, is7_source = legacy.descriptors(is7_path, catalog_version=1)
    if ms1['type_name'] != 'ussr:MS-1' or is7['type_name'] != 'ussr:IS-7':
        raise ValueError('measured MS-1 and IS-7 native inputs required')
    before = original.get('selection_before')
    if (type(original.get('version')) is not int or original['version'] != 1
            or type(before) is not dict or set(before) != {
                'database_id', 'selected_inventory_id', 'selected_descriptor_sha256'}
            or before != original.get('selection_after')):
        raise ValueError('native readonly export preservation evidence missing')
    bounded_int(before['database_id'], 'observed native account ID', 1)
    bounded_int(before['selected_inventory_id'], 'observed selected inventory ID', 1)
    if before['selected_descriptor_sha256'] != digest(bytes.fromhex(ms1['compact_descr_hex'])):
        raise ValueError('readonly export did not preserve measured MS-1 selection')
    actual_components = original['vehicle'].get('components')
    if type(actual_components) is not dict or set(actual_components) != set(COMPONENTS):
        raise ValueError('actual native component identities absent')
    for kind in COMPONENTS:
        item = actual_components[kind]
        if type(item) is not dict or set(item) != {'id', 'compact_descr'}:
            raise ValueError('actual native component identity schema')
        cd = bounded_int(item['compact_descr'], 'actual component CD')
        if item['id'] != [0, cd >> 8] or any(type(x) is not int for x in item['id']):
            raise ValueError('actual native component identity mismatch')
    _, paths = config()
    prices, sources = is7_reference_prices(is7, paths['original_client_root'])
    is7['mounted_module_prices'] = prices
    is7['vehicle_dossier'] = legacy.bounded_hex(original.get('vehicle_dossier_hex'), 'native vehicle dossier', 4096)
    # Validate the original layout before any proposed timestamp change.
    grant_vehicle_dossier(is7['vehicle_dossier'], 1000)
    is7_source['mounted_module_price_sources'] = sources
    return ms1, is7, {'ms1': ms1_source, 'is7': is7_source}


def build_payloads(profile, base, base_sha256, ms1, is7):
    verify_encoder()
    validate_profile(profile, base, base_sha256)
    model, compatibility, trees = legacy.fixture(ms1, base, catalog_version=2)
    previous = deepcopy(trees)
    state, shop = trees['state.bin'], trees['shop.bin']
    cd, inventory_id = is7['type_compact_descr'], 2
    if cd != 7169 or is7['max_health'] != 2150:
        raise ValueError('measured IS-7 native mapping required')
    inventory = state['inventory'][1]
    additions = {'compDescr': bytes.fromhex(is7['compact_descr_hex']), 'repair': (0, 2150),
                 'crew': [None] * 5, 'settings': 0, 'shells': [], 'shellsLayout': {},
                 'eqs': [0, 0, 0], 'eqsLayout': [0, 0, 0]}
    for field, item in additions.items():
        if inventory_id in inventory[field]:
            raise ValueError('IS-7 native inventory ID already occupied')
        inventory[field][inventory_id] = item
    state['stats']['vehTypeXP'][cd] = 0
    state['stats']['unlocks'].extend(x for x in [cd] + sorted(set(is7['components'].values()))
                                     if x not in state['stats']['unlocks'])
    prices = is7['mounted_module_prices']
    if set(prices) != {is7['components'][key] for key in VISIBLE_COMPONENTS} or len(prices) != 5:
        raise ValueError('exactly five mounted IS-7 display references required')
    shop['rev'] = CATALOG_REVISION
    for item_cd, price in [(cd, is7['reference_price'])] + sorted(prices.items()):
        if item_cd in shop['items']['itemPrices']:
            raise ValueError('new IS-7 reference collides with preserved MS-1 catalogue')
        if type(price) is not tuple or len(price) != 2:
            raise ValueError('reference price pair required')
        for amount in price:
            bounded_int(amount, 'reference price')
        shop['items']['itemPrices'][item_cd] = price
        shop['items']['notInShopItems'].append(item_cd)
    stamp = profile['test_grant']['granted_at_ms'] // 1000
    dossier = grant_vehicle_dossier(is7['vehicle_dossier'], profile['test_grant']['granted_at_ms'])
    trees['dossier.bin'] = (DOSSIER_CACHE_VERSION, [(cd, stamp, dossier)])
    model.update(fixture_version=PROFILE_VERSION, profile_version=PROFILE_VERSION,
                 snapshot_revision=SNAPSHOT_REVISION, inventory=deepcopy(profile['inventory']),
                 test_grant=deepcopy(profile['test_grant']))
    compatibility.update(compatibility_catalog_revision=CATALOG_REVISION,
                         snapshot_revision=SNAPSHOT_REVISION, wire_sync_revision=WIRE_SYNC_REVISION)
    compatibility['vehicle_mapping'].append({
        'inventory_id': profile['inventory'][1]['inventory_id'], 'native_inventory_id': inventory_id,
        'type_compact_descr': cd, 'descriptor_source': 'actual UI06 original VehicleDescr export; local evidence'})
    preservation = verify_delta(previous, trees, base, profile, is7)
    compatibility['dossier_cache'] = {key: preservation['dossier_cache'][key] for key in
                                     ('version', 'last_change_time', 'vehicle_type_compact_descr')}
    return model, compatibility, trees, preservation


def verify_delta(previous, current, base, profile, is7):
    """Reversing only the declared grant delta must recover the exact old trees."""
    restored = deepcopy(current)
    before = previous['state.bin']
    after = restored['state.bin']
    if after['rev'] != WIRE_SYNC_REVISION or before['rev'] != WIRE_SYNC_REVISION:
        raise ValueError('native session sync revision changed')
    expected_additions = {'compDescr': bytes.fromhex(is7['compact_descr_hex']), 'repair': (0, 2150),
                          'crew': [None] * 5, 'settings': 0, 'shells': [], 'shellsLayout': {},
                          'eqs': [0, 0, 0], 'eqsLayout': [0, 0, 0]}
    for field in before['inventory'][1]:
        if set(after['inventory'][1][field]) != {1, 2}:
            raise ValueError('unexpected inventory identity delta')
        if after['inventory'][1][field][2] != expected_additions[field]:
            raise ValueError('new vehicle differs from exact measured test grant')
        del after['inventory'][1][field][2]
    if after['stats']['vehTypeXP'].get(7169) != 0:
        raise ValueError('test grant invented IS-7 experience')
    del after['stats']['vehTypeXP'][7169]
    allowed_unlocks = set(before['stats']['unlocks']) | {7169} | set(is7['components'].values())
    if set(after['stats']['unlocks']) != allowed_unlocks or len(after['stats']['unlocks']) != len(allowed_unlocks):
        raise ValueError('grant unlocked an unrelated component')
    after['stats']['unlocks'] = [x for x in after['stats']['unlocks'] if x in before['stats']['unlocks']]
    if legacy.encode_data(after) != legacy.encode_data(before):
        raise ValueError('grant changed account state outside declared IS-7 additions')
    shop, old_shop = restored['shop.bin'], previous['shop.bin']
    expected_prices = {7169: is7['reference_price'], **is7['mounted_module_prices']}
    if set(shop['items']['itemPrices']) != set(old_shop['items']['itemPrices']) | set(expected_prices):
        raise ValueError('unexpected test garage reference catalogue item')
    for item_cd, price in expected_prices.items():
        if shop['items']['itemPrices'].pop(item_cd) != price:
            raise ValueError('test garage reference price changed')
    new_hidden = shop['items']['notInShopItems']
    if set(new_hidden) != set(old_shop['items']['notInShopItems']) | set(expected_prices) or len(new_hidden) != len(set(new_hidden)):
        raise ValueError('unexpected hidden reference catalogue item')
    shop['items']['notInShopItems'] = [cd for cd in new_hidden if cd not in expected_prices]
    if shop['rev'] != CATALOG_REVISION:
        raise ValueError('test garage catalogue revision changed')
    shop['rev'] = old_shop['rev']
    if legacy.encode_data(shop) != legacy.encode_data(old_shop):
        raise ValueError('grant changed unrelated catalogue state')
    stamp = profile['test_grant']['granted_at_ms']
    expected_dossier = (DOSSIER_CACHE_VERSION, [(7169, stamp // 1000,
                                               grant_vehicle_dossier(is7['vehicle_dossier'], stamp))])
    if current['dossier.bin'] != expected_dossier or previous['dossier.bin'] != (0, []):
        raise ValueError('unexpected dossier/history delta')
    for key in ('account_id', 'username', 'native_database_id', 'created_at_ms', 'resources', 'statistics'):
        if profile[key] != base[key]:
            raise ValueError('grant changed persisted identity/resources/history')
    return {'status': 'PASS_LOCAL_INVARIANTS_ONLY',
            'account_and_ms1_restored_state_sha256': digest(legacy.encode_data(after)),
            'base_state_sha256': digest(legacy.encode_data(before)),
            'account_dossier_sha256': digest(before['stats']['dossier']),
            'ms1_descriptor_sha256': digest(before['inventory'][1]['compDescr'][1]),
            'base_dossier_payload_sha256': digest(legacy.encode_data(previous['dossier.bin'])),
            'base_shop_sha256': digest(legacy.encode_data(previous['shop.bin'])),
            'restored_shop_sha256': digest(legacy.encode_data(shop)),
            'dossier_cache': {'version': DOSSIER_CACHE_VERSION, 'last_change_time': stamp // 1000,
                              'vehicle_type_compact_descr': 7169,
                              'payload_sha256': digest(legacy.encode_data(current['dossier.bin']))},
            'delta': ['inventory[vehicle] key2 only', 'vehTypeXP[7169]=0', 'owned IS-7/mounted unlock references',
                      'shop revision3 and six IS-7 display references', 'vehicle dossier owner7169 only'],
            'native_compatibility': 'NOT_RUN; local generation is not native acceptance'}


def generate(profile_path, base_profile_path, ms1_path, is7_path, out):
    dependency = verify_encoder()
    base, base_source, base_raw = read_base_profile(base_profile_path)
    profile_path = local_file(profile_path)
    profile_raw = read_limited(profile_path, 8192)
    profile = validate_profile(bounded_json(profile_raw), base, base_source['sha256'])
    ms1, is7, native_sources = read_native_inputs(ms1_path, is7_path)
    model, compatibility, trees, preservation = build_payloads(profile, base, base_source['sha256'], ms1, is7)
    payloads = {name: legacy.encode_data(tree) for name, tree in trees.items()}
    target = local_file(out, exists=False)
    if target.exists():
        allowed = {'profile-input.json'} if profile_path.parent == target and profile_path.name == 'profile-input.json' else set()
        if {x.name for x in target.iterdir()} != allowed:
            raise FileExistsError('append-only garage snapshot: use a fresh output directory')
    else:
        target.mkdir(parents=True, exist_ok=False)
    sources = {}
    for filename, raw in (('profile-input.json', profile_raw), ('base-profile-input.json', base_raw)):
        destination = target / filename
        if destination.exists():
            if filename != 'profile-input.json' or destination.read_bytes() != raw:
                raise FileExistsError('snapshot input would be overwritten')
        else:
            with destination.open('xb') as stream:
                stream.write(raw)
        sources[filename] = {'file': filename, 'relative_to': 'fixture_directory', 'sha256': digest(raw)}
    files = []
    for name, raw in payloads.items():
        with (target / name).open('xb') as stream:
            stream.write(raw)
        files.append({'file': name, 'bytes': len(raw), 'sha256': digest(raw),
                      'opcodes': sorted(set(op.name for op, _, _ in pickletools.genops(raw)))})
    manifest = {'fixture_version': PROFILE_VERSION, 'ruleset': 'test_lab', 'profile_version': PROFILE_VERSION,
                'snapshot_revision': SNAPSHOT_REVISION, 'wire_sync_revision': WIRE_SYNC_REVISION,
                'compatibility_catalog_revision': CATALOG_REVISION, 'account_id': profile['account_id'],
                'native_database_id': profile['native_database_id'], 'profile_source': sources['profile-input.json'],
                'base_profile_source': sources['base-profile-input.json'], 'native_descriptors': native_sources,
                'generator': {'file': str(Path(__file__).resolve()), 'sha256': sha256(Path(__file__)),
                              'dependency': dependency}, 'files': files,
                'native_compatibility': 'NOT_RUN; requires original client receiving actual server streams',
                'preservation': preservation, 'grant': profile['test_grant']}
    if len(manifest) > 16 or len(json.dumps(manifest).encode('utf8')) > 32768:
        raise ValueError('native loader manifest bound exceeded')
    for filename, value in (('fixture.json', model), ('compatibility.json', compatibility),
                            ('payloads.json', {name: legacy.json_tree(tree) for name, tree in trees.items()}),
                            ('preservation.json', preservation), ('manifest.json', manifest)):
        save_json(target / filename, value)
    return {'output': str(target), 'account_id': profile['account_id'], 'files': files,
            'snapshot_revision': SNAPSHOT_REVISION, 'wire_sync_revision': WIRE_SYNC_REVISION,
            'compatibility_catalog_revision': CATALOG_REVISION, 'native_compatibility': 'NOT_RUN'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    promote = commands.add_parser('promote', help='Write a deterministic proposed profile2; no persistence mutation')
    promote.add_argument('--profile-v1', required=True)
    promote.add_argument('--granted-at-ms', type=int, required=True)
    promote.add_argument('--out-profile', required=True)
    build = commands.add_parser('generate', help='Write one immutable native representation of an explicit profile2')
    for name in ('profile', 'base-profile', 'native-ms1', 'native-is7', 'out'):
        build.add_argument('--' + name, required=True)
    args = parser.parse_args()
    if args.command == 'promote':
        verify_encoder()
        base, source, _ = read_base_profile(args.profile_v1)
        proposed = promote_profile(base, source['sha256'], args.granted_at_ms)
        target = local_file(args.out_profile, exists=False)
        target.parent.mkdir(parents=True, exist_ok=True)
        save_json(target, proposed)
        print(json.dumps({'output': str(target), 'sha256': sha256(target), 'status': 'PROPOSAL_ONLY_NO_DB_WRITE'}))
    else:
        print(json.dumps(generate(args.profile, args.base_profile, args.native_ms1, args.native_is7, args.out)))


if __name__ == '__main__':
    main()
