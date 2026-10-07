"""Independent native acceptance for the explicit two-vehicle test garage.

Reads immutable evidence only. Never imports/runs a fixture generator, launches
the client, controls input, writes a profile or unpickles executable objects.
Unit inputs test rejection logic; native compatibility requires actual captures.
"""
import argparse
import copy
from datetime import datetime
from pathlib import Path
import re
import struct

import verify_hangar_ui as ui
import verify_unified_entry as entry
from client_audit import ROOT, config, output_dir, read_limited, save_json
from packed_xml import decode, walk
from verify_hangar import digest, local_file, mo_literal, require


TOOL = 'verify_test_garage'
SCHEMA = 1
GENERATOR_SHA = 'dec1f884dd8b22ef0d4a6c21389cb37c075f008feb6a12bc7d43888c5b4c5825'
EXPORT_SHA = '4b24a59c5344808018caf438c044d31d86cf1da20c8b2cbd58f93b8ab2f859b1'
EVIDENCE = ROOT / 'local/evidence/20261004-p02-hangar-ui'
XML_SHA = {**ui.CATALOG_XML,
           'is-7.xml': '8d55fa4657a88f1436cd164afe11bade875a906fa7b97256f1fb2f803b09c10d',
           'list.xml': '167a637d725a233d42e52bd7d5bac00b9af45c0ef225163ab578e202454f5138'}
# Values below are measured #717 native descriptors/XML references, not prices
# made authoritative by a client. All six references remain unavailable to trade.
COMPONENTS = {
    'chassis': (58, 14850, 'chassis.xml', 'IS-7', 'is-7.xml', '/chassis[1]/IS-7[1]/price[1]', '82500.0', 82500),
    'engine': (36, 9221, 'engines.xml', 'M-50T', 'components/engines.xml', '/shared[1]/M-50T[1]/price[1]', 132000, 132000),
    'radio': (11, 2823, 'radios.xml', '_10RK-26', 'components/radios.xml', '/shared[1]/_10RK-26[1]/price[1]', 51600, 51600),
    'turret': (47, 12035, 'turrets.xml', 'IS-7', 'is-7.xml', '/turrets0[1]/IS-7[1]/price[1]', '66000.0', 66000),
    'gun': (58, 14852, 'guns.xml', '_130mm_S-70', 'components/guns.xml', '/shared[1]/_130mm_S-70[1]/price[1]', 297000, 297000),
}
NATIVE_COMPONENTS = {k: {'id': [0, v[0]], 'compact_descr': v[1]} for k, v in COMPONENTS.items()}
NATIVE_COMPONENTS['fuelTank'] = {'id': [0, 205], 'compact_descr': 52486}
IS7_NATIVE = {'type_name': 'ussr:IS-7', 'type_id': [0, 28], 'type_compact_descr': 7169,
              'compact_descr_hex': '011c3a002400cd000b002f003a0000', 'max_health': 2150,
              'crew_roles': [['commander'], ['gunner'], ['driver'], ['loader'], ['loader', 'radioman']],
              'components': NATIVE_COMPONENTS}
IS7_OBSERVED = {'inventory_id': 2, 'type_compact_descr': 7169, 'type_name': 'ussr:IS-7',
                'health': 2150, 'max_health': 2150, 'xp': 0, 'crew_slots': 5}
PROFILE_BASE_KEYS = {'profile_version', 'account_id', 'username', 'native_database_id',
                     'created_at_ms', 'snapshot_revision', 'resources', 'statistics'}
READY = {'gui_initialized': True, 'interactive_movie_started': True, 'native_connected': True,
         'window_class': 'AppEntry', 'app_initialized': True, 'hangar_space_inited': True,
         'hangar_space_loaded': True, 'hangar_space_loading': False, 'waiting_visible': False,
         'items_cache_synced': True, 'vehicle_model_loaded': True}
COMMON_NATIVE_CHECKS = ('original_bytecode', 'native_website_identity', 'original_account_lifecycle',
                       'native_rpc_correlated_returns', 'native_show_gui_return', 'native_server_stats_returns',
                       'native_stream_integrity_returns', 'native_resources_statistics', 'transport_beyond_old_limit')


def same(left, right, message):
    require(entry.same_literal(left, right), message)


def missing(reason):
    return {'status': 'NOT_RUN', 'reason': reason}


def checked(function):
    try:
        return function()
    except FileNotFoundError as error:
        return missing(str(error))
    except ui.FAILURES as error:
        return {'status': 'FAIL', 'error_type': type(error).__name__, 'error': str(error)}


def profile_delta(base_raw, profile, grant):
    base = entry.json_data(base_raw)
    require(type(base) is dict and set(base) == PROFILE_BASE_KEYS, 'unmeasured historical profile schema')
    require(type(profile) is dict and set(profile) == PROFILE_BASE_KEYS | {'inventory', 'test_grant'},
            'snapshot2 profile schema')
    require(type(grant) is dict and set(grant) == {'grant_id', 'granted_at_ms', 'base_profile_sha256'}, 'grant schema')
    stamp = grant.get('granted_at_ms')
    require(grant.get('grant_id') == 'test-is7-v1' and type(stamp) is int
            and base['created_at_ms'] <= stamp <= 2147483647999 and stamp // 1000 > 0
            and grant.get('base_profile_sha256') == digest(base_raw), 'grant identity/time/exact base bytes')
    same(profile['test_grant'], grant, 'manifest/profile grant differs')
    previous = {k: profile[k] for k in PROFILE_BASE_KEYS}
    require(type(profile['profile_version']) is int and profile['profile_version'] == 2
            and type(profile['snapshot_revision']) is int and profile['snapshot_revision'] == 2,
            'snapshot2 domain revisions')
    previous.update(profile_version=1, snapshot_revision=1)
    same(previous, base, 'grant changed prior UUID, name, native ID, date, resources or history')
    same(profile['statistics'], {'battles': 0, 'wins': 0, 'losses': 0, 'draws': 0}, 'invented battle history')
    wanted = []
    for suffix, definition, health in (('starter-vehicle-v1', 'vehicle:ms1', 90), ('test-is7-v1', 'vehicle:is7', 2150)):
        wanted.append({'inventory_id': profile['account_id'] + ':' + suffix, 'vehicle_definition_id': definition,
                       'health': health, 'vehicle_xp': 0, 'crew_assigned': False, 'ammunition_count': 0})
    same(profile['inventory'], wanted, 'not the exact two uncrewed/unarmed test vehicles')
    return stamp // 1000


def native_provenance(source, old_source, local_root):
    require(type(source) is dict and set(source) == {'ms1', 'is7'}, 'native descriptor source set')
    # The service keeps an exact owned copy of the measured exporter output.
    # Path spelling may differ; bytes and all resource provenance may not.
    same({k: v for k, v in source['ms1'].items() if k != 'file'},
         {k: v for k, v in old_source.items() if k != 'file'}, 'MS-1 descriptor provenance changed')
    old_ms1 = read_limited(entry.owned(old_source['file'], local_root), 32768)
    new_ms1 = read_limited(entry.owned(source['ms1']['file'], local_root), 32768)
    require(old_ms1 == new_ms1 and len(new_ms1) == source['ms1']['bytes']
            and digest(new_ms1) == source['ms1']['sha256'], 'MS-1 export bytes changed between owned copies')
    metadata = source['is7']
    path = entry.owned(metadata['file'], local_root)
    raw = read_limited(path, 32768)
    require(metadata.get('bytes') == len(raw) == 1290 and metadata.get('sha256') == digest(raw) == EXPORT_SHA,
            'not the measured readonly native IS-7 export')
    native = entry.json_data(raw)
    same(native['vehicle'], IS7_NATIVE, 'native IS-7 constructor/roles/components differ')
    same(native['selection_before'], native['selection_after'], 'native export changed selected vehicle')
    trace = EVIDENCE / 'ui06-catalog2-manual-runtime/native-84612-1791125424030.jsonl'
    trace_raw = read_limited(trace, 17 * 1024 * 1024)
    exports = [(i + 1, entry.json_data(line)) for i, line in enumerate(trace_raw.splitlines())
               if b'"original_vehicle_export"' in line]
    require(len(exports) == 1 and exports[0][1].get('selection_unchanged') is True
            and exports[0][1]['output'].get('sha256') == EXPORT_SHA, 'native export lacks matching runtime proof')
    exported_path = entry.owned(exports[0][1]['output']['path'], local_root)
    require(read_limited(exported_path, 32768) == raw, 'owned IS-7 descriptor copy differs from the native-exported file')
    original = config()[1]['original_client_root'].resolve()
    directory = original / 'res/scripts/item_defs/vehicles/ussr'
    sources, values = [], {}

    def resource(relative):
        if relative not in values:
            target = (directory / relative).resolve(strict=True)
            require(target.is_relative_to(original), 'resource outside original client')
            data = read_limited(target, 2 * 1024 * 1024)
            require(digest(data) == XML_SHA[relative], 'unmeasured original XML hash')
            values[relative] = (target, dict(walk(decode(data, max_bytes=2 * 1024 * 1024))))
        return values[relative]

    def source_node(row, relative, node, value, field='source_value'):
        target, nodes = resource(relative)
        require(Path(row['file']).resolve(strict=True) == target and row.get('sha256') == XML_SHA[relative]
                and row.get('node') == node, 'IS-7 XML provenance identity differs')
        same(nodes.get(node), value, 'original IS-7 XML value changed')
        same(row.get(field), value, 'provenance value differs from original XML')
        sources.append({'file': str(target), 'sha256': XML_SHA[relative], 'node': node, 'value': value})
        return nodes

    price_source = metadata['reference_price_source']
    nodes = source_node(price_source, 'list.xml', '/IS-7[1]/price[1]', 6100000)
    require(price_source.get('gold_child_present') is False and '/IS-7[1]/price[1]/gold[1]' not in nodes
            and nodes.get('/IS-7[1]/id[1]') == 28, 'IS-7 vehicle ID/reference currency')
    rows = metadata['mounted_module_price_sources']
    require(type(rows) is list and len(rows) == 5 and {r.get('component') for r in rows} == set(COMPONENTS),
            'must reference precisely the five actually mounted modules')
    prices = {7169: (6100000, 0)}
    for row in rows:
        kind = row['component']
        local_id, cd, id_file, name, price_file, node, raw_price, amount = COMPONENTS[kind]
        require(type(row.get('compact_descr')) is int and row['compact_descr'] == cd, 'wrong mounted module ID')
        source_node(row['id_source'], 'components/' + id_file, '/ids[1]/' + name + '[1]', local_id)
        price = row['price_source']
        nodes = source_node(price, price_file, node, raw_price, 'raw_value')
        require(type(price.get('integral_value')) is int and price['integral_value'] == amount
                and price.get('gold_child_present') is False and node + '/gold[1]' not in nodes, 'module reference amount/currency')
        prices[cd] = (amount, 0)
    _, vehicle_xml = resource('is-7.xml')
    require(vehicle_xml['/hull[1]/maxHealth[1]'] + vehicle_xml['/turrets0[1]/IS-7[1]/maxHealth[1]'] == 2150,
            'native IS-7 HP differs from original hull/turret')
    return native, prices, {'status': 'PASS', 'native_export': str(exported_path), 'fixture_source_copy': str(path), 'sha256': EXPORT_SHA,
                             'native_trace': str(trace), 'trace_sha256': digest(trace_raw),
                             'trace_line': exports[0][0], 'original_resources': sources}


def payload_delta(before, after, native, prices, seconds):
    """Reverse only measured additions; compare decoded historical data exactly."""
    old_state, old_shop, old_dossier = (entry.literal(before[n]) for n in ('state.bin', 'shop.bin', 'dossier.bin'))
    state, shop, dossier = (entry.literal(after[n]) for n in ('state.bin', 'shop.bin', 'dossier.bin'))
    restored = copy.deepcopy(state)
    require(type(state.get(b'rev')) is int and state[b'rev'] == old_state[b'rev'] == 1, 'wire sync revision changed')
    additions = {b'compDescr': bytes.fromhex(native['vehicle']['compact_descr_hex']), b'repair': (0, 2150),
                 b'crew': [None] * 5, b'settings': 0, b'shells': [], b'shellsLayout': {},
                 b'eqs': [0, 0, 0], b'eqsLayout': [0, 0, 0]}
    inventory = restored[b'inventory'][1]
    require(set(inventory) == set(additions), 'unexpected vehicle inventory field')
    for key, value in additions.items():
        require(type(inventory[key]) is dict and set(inventory[key]) == {1, 2}, 'unexpected native inventory ID')
        same(inventory[key].pop(2), value, 'IS-7 inventory value does not match the explicit test grant')
    same(restored[b'stats'][b'vehTypeXP'].pop(7169), 0, 'invented IS-7 XP')
    old_unlocks = old_state[b'stats'][b'unlocks']
    unlocks = restored[b'stats'][b'unlocks']
    expected_unlocks = set(old_unlocks) | {7169} | {v['compact_descr'] for v in native['vehicle']['components'].values()}
    require(type(unlocks) is list and all(type(x) is int for x in unlocks)
            and len(unlocks) == len(set(unlocks)) and set(unlocks) == expected_unlocks, 'unrelated or duplicate unlock added')
    restored[b'stats'][b'unlocks'] = [value for value in unlocks if value in old_unlocks]
    same(restored, old_state, 'MS-1/account state changed outside the explicit grant')
    restored_shop = copy.deepcopy(shop)
    require(type(shop.get(b'rev')) is int and shop[b'rev'] == 3 and old_shop[b'rev'] == 2, 'catalogue revision2 to3 required')
    restored_shop[b'rev'] = 2
    catalog = restored_shop[b'items']
    require(set(catalog[b'itemPrices']) == set(old_shop[b'items'][b'itemPrices']) | set(prices), 'unexpected catalogue item')
    for cd, price in prices.items():
        same(catalog[b'itemPrices'].pop(cd), price, 'reference price differs from original XML')
    hidden = catalog[b'notInShopItems']
    require(type(hidden) is list and all(type(x) is int for x in hidden) and len(hidden) == len(set(hidden))
            and set(hidden) == set(old_shop[b'items'][b'notInShopItems']) | set(prices), 'issued references must remain unavailable to trade')
    catalog[b'notInShopItems'] = [cd for cd in hidden if cd not in prices]
    same(restored_shop, old_shop, 'unrelated old shop data changed')
    same(old_dossier, (0, []), 'unmeasured historical vehicle dossier baseline')
    original = bytes.fromhex(native['vehicle_dossier_hex'])
    require(len(original) == 70, 'native vehicle dossier length')
    header = struct.unpack_from('<26H', original)
    require(header[0] == 81 and header[10] == 18 and sum(header[1:]) == 18 and not any(original[56:]),
            'native vehicle dossier is not empty version81')
    wanted = original[:52] + struct.pack('<I', seconds) + original[56:]
    same(dossier, (1, [(7169, seconds, wanted)]), 'dossier owner/time/version/zero-history delta differs')
    return {'status': 'PASS', 'base_state_sha256': digest(before['state.bin']),
            'base_shop_sha256': digest(before['shop.bin']), 'base_dossier_sha256': digest(before['dossier.bin']),
            'account_dossier_sha256': digest(old_state[b'stats'][b'dossier']),
            'ms1_descriptor_sha256': digest(old_state[b'inventory'][1][b'compDescr'][1]),
            'preserved': 'All historical primitive values and existing byte strings are exact; no regeneration used.',
            'dossier_cache': {'version': 1, 'last_change_time': seconds, 'vehicle_type_compact_descr': 7169}}


def garage_fixture(fixture, base_fixture, baseline, local_root):
    raw_manifest = local_file(fixture, 'manifest.json', 65536)
    manifest = entry.json_data(raw_manifest)
    keys = {'fixture_version', 'ruleset', 'profile_version', 'snapshot_revision', 'wire_sync_revision',
            'compatibility_catalog_revision', 'account_id', 'native_database_id', 'profile_source', 'base_profile_source',
            'native_descriptors', 'generator', 'files', 'native_compatibility', 'preservation', 'grant'}
    require(type(manifest) is dict and set(manifest) == keys and len(manifest) == 16, 'unknown snapshot2 manifest schema')
    for key, value in {'fixture_version': 2, 'profile_version': 2, 'snapshot_revision': 2,
                       'wire_sync_revision': 1, 'compatibility_catalog_revision': 3, 'ruleset': 'test_lab',
                       'account_id': baseline['account_id'], 'native_database_id': baseline['native_id']}.items():
        same(manifest[key], value, 'snapshot2 manifest identity/revision: ' + key)
    generator = manifest['generator']
    require(generator.get('sha256') == GENERATOR_SHA
            and generator.get('dependency', {}).get('sha256') == ui.CATALOG_GENERATOR_SHA, 'unmeasured generator provenance')
    base_raw = local_file(base_fixture, 'profile-input.json', 8192)
    require(local_file(fixture, 'base-profile-input.json', 8192) == base_raw, 'exact historical profile input not preserved')
    profile_raw = local_file(fixture, 'profile-input.json', 8192)
    profile = entry.json_data(profile_raw)
    for key, filename, data in (('profile_source', 'profile-input.json', profile_raw),
                                ('base_profile_source', 'base-profile-input.json', base_raw)):
        same(manifest[key], {'file': filename, 'relative_to': 'fixture_directory', 'sha256': digest(data)}, 'profile source hash/path differs')
    seconds = profile_delta(base_raw, profile, manifest['grant'])
    native, prices, provenance = native_provenance(manifest['native_descriptors'], baseline['manifest']['native_descriptors'], local_root)
    files, raw = manifest['files'], {}
    require(type(files) is list and len(files) == 3 and {r.get('file') for r in files} == {'state.bin', 'shop.bin', 'dossier.bin'}, 'fixture member list')
    for row in files:
        data = local_file(fixture, row['file'], entry.MAX_RAW)
        require(type(row.get('bytes')) is int and row['bytes'] == len(data) and row.get('sha256') == digest(data), 'payload size/hash mismatch')
        entry.literal(data)
        raw[row['file']] = data
    delta = payload_delta(baseline['raw'], raw, native, prices, seconds)
    policy = delta['dossier_cache']
    preservation = manifest['preservation']
    same(preservation.get('dossier_cache'), {**policy, 'payload_sha256': digest(raw['dossier.bin'])}, 'manifest dossier cache differs from raw tuple')
    for key, expected in (('base_state_sha256', delta['base_state_sha256']),
                          ('account_and_ms1_restored_state_sha256', delta['base_state_sha256']),
                          ('base_shop_sha256', delta['base_shop_sha256']), ('restored_shop_sha256', delta['base_shop_sha256']),
                          ('base_dossier_payload_sha256', delta['base_dossier_sha256']),
                          ('account_dossier_sha256', delta['account_dossier_sha256']), ('ms1_descriptor_sha256', delta['ms1_descriptor_sha256'])):
        require(preservation.get(key) == expected, 'preservation hash differs from actual baseline: ' + key)
    compatibility_raw = local_file(fixture, 'compatibility.json', 65536)
    compatibility = entry.json_data(compatibility_raw)
    previous_compat = entry.json_data(local_file(base_fixture, 'compatibility.json', 65536))
    wanted = copy.deepcopy(previous_compat)
    wanted.update(compatibility_catalog_revision=3, snapshot_revision=2, wire_sync_revision=1, dossier_cache=policy)
    wanted['vehicle_mapping'].append({'inventory_id': profile['inventory'][1]['inventory_id'], 'native_inventory_id': 2,
                                      'type_compact_descr': 7169, 'descriptor_source': 'actual UI06 original VehicleDescr export; local evidence'})
    same(compatibility, wanted, 'native mapping differs from stable account/two-vehicle grant')
    # Analysis adapter for common Account checks; manifest on disk stays untouched.
    expected = {**baseline, 'raw': raw, 'manifest': {**manifest, 'statistics': profile['statistics']},
                'manifest_sha256': digest(raw_manifest), 'profile': profile, 'dossier_cache': policy,
                'vehicles': {1: baseline['vehicle'], 2: IS7_OBSERVED},
                'vehicle_display_names': {1: baseline['vehicle_display_name'],
                    2: mo_literal('ussr_vehicles.mo', '8293bf404fa3bdbf724b3c4e8ac817c6f0bd9ba90a73ba27e8856d9b3b9bf7f1', 'IS-7')}}
    return expected, {'status': 'PASS', 'manifest_sha256': digest(raw_manifest), 'profile_sha256': digest(profile_raw),
                       'base_profile_sha256': digest(base_raw), 'compatibility_sha256': digest(compatibility_raw),
                       'delta': delta, 'native_provenance': provenance,
                       'scope': 'Independent local fixture/provenance checks only. Native delivery and render checked separately.'}


def ready(row, vehicles):
    vehicle = row.get('vehicle') or {}
    number = row.get('selected_inventory_id')
    views = row.get('views') or {}
    main, sub = views.get('main') or {}, views.get('lobby_sub') or {}
    models = row.get('vehicle_models_visible', [])
    return (type(number) is int and number in vehicles and entry.same_literal(vehicle, vehicles[number])
            and all(type(row.get(k)) is type(v) and row[k] == v for k, v in READY.items())
            and main.get('class_name') == 'LobbyView' and main.get('alias') == 'lobby'
            and main.get('flash_bound') is True and 'lobbyHeader' in main.get('components', [])
            and sub.get('class_name') == 'Hangar' and sub.get('alias') == 'hangar'
            and sub.get('flash_bound') is True and {'tankCarousel', 'params'} <= set(sub.get('components', []))
            and type(row.get('visual_entity_id')) is int and row['visual_entity_id'] > 0
            and type(row.get('vehicle_model_count')) is int and 1 <= row['vehicle_model_count'] <= 16
            and type(models) is list and len(models) == row['vehicle_model_count'] and all(x is True for x in models))


def garage_observations(rows, expected, minimum):
    require(type(minimum) in (int, float) and 60 <= minimum <= 1800, 'two-vehicle minimum ready policy is >=60 seconds')
    samples = [r for r in rows if r['event'] == 'native_hangar']
    require(samples, 'native Hangar observations absent')
    vehicles = expected['vehicles']
    for row in samples:
        vehicle = row.get('vehicle')
        if row.get('items_cache_synced') is True and vehicle is not None:
            number = row.get('selected_inventory_id')
            require(type(number) is int and number in vehicles, 'unknown native selected vehicle')
            same(vehicle, vehicles[number], 'observed descriptor/HP/XP/crew differs from server grant')
    tabs = [r['elapsed_seconds'] for r in rows if
            (r['event'] == 'native_hangar' and ((r.get('views') or {}).get('lobby_sub') or {}).get('class_name') == 'ProfilePage')
            or (r['event'] == 'native_profile_call' and r.get('phase') == 'call')]
    first_tab = min(tabs) if tabs else None
    full, run, runs = [], [], []
    for row in samples:
        valid = ready(row, vehicles)
        before = first_tab is None or row['elapsed_seconds'] < first_tab
        if not valid or not before or (run and (row['elapsed_seconds'] - run[-1]['elapsed_seconds'] > 3
                                              or row['selected_inventory_id'] != run[-1]['selected_inventory_id'])):
            if run:
                runs.append(run)
            run = []
        if valid:
            full.append(row)
            if before:
                run.append(row)
    if run:
        runs.append(run)
    longest = max(runs, key=lambda value: value[-1]['elapsed_seconds'] - value[0]['elapsed_seconds'], default=[])
    seconds = longest[-1]['elapsed_seconds'] - longest[0]['elapsed_seconds'] if longest else 0
    sequence = []
    for row in full:
        number = row['selected_inventory_id']
        if not sequence or sequence[-1]['inventory_id'] != number:
            sequence.append({'inventory_id': number, 'seconds': row['elapsed_seconds'], 'observation_index': row.get('observation_index')})
    ids = [r['inventory_id'] for r in sequence]
    cycle = any(ids[i:i + 3] in ([1, 2, 1], [2, 1, 2]) for i in range(max(0, len(ids) - 2)))
    measured = {str(n): {'ready_samples': sum(r['selected_inventory_id'] == n for r in full), 'expected': value}
                for n, value in vehicles.items()}
    return {'readiness': ui.result(len(longest) >= 5 and seconds >= minimum,
                                   continuous_seconds=seconds, minimum_seconds=minimum, continuous_samples=len(longest),
                                   first_profile_seconds=first_tab, maximum_sample_gap_seconds=3, vehicles=measured),
            'selection_cycle': ({'status': 'PASS', 'sequence': sequence, 'vehicles': measured,
                                 'scope': 'Actual ready native models selected and returned; no server or observer selection.'}
                                if cycle else {**missing('Both native models and a return were not observed'), 'sequence': sequence, 'vehicles': measured})}


def tank_header(rows, expected):
    names = {n: value['value'] for n, value in expected['vehicle_display_names'].items()}
    selected = [r for r in rows if r['event'] == 'native_header_call' and r.get('method') == 'as_setTankNameS']
    if not selected:
        return missing('Original tank-name Flash callback was not observed')
    pending, pairs = [], []
    for row in selected:
        require(row.get('source') == 'scripts/client/gui/Scaleform/daapi/view/meta/LobbyHeaderMeta.py'
                and row.get('source_line') == 202 and row.get('flash_bound') is True,
                'tank header source/Flash binding mismatch')
        require(row.get('name') in names.values(), 'header shows an unissued or wrong localized vehicle')
        if row.get('phase') == 'call':
            pending.append(row)
        else:
            require(row.get('phase') == 'return' and pending and row.get('offset') == 27, 'tank header did not return via original branch')
            call = pending.pop()
            require(call['name'] == row['name'] and call['elapsed_seconds'] <= row['elapsed_seconds'], 'tank header call/return mismatch')
            pairs.append({'call_seconds': call['elapsed_seconds'], 'return_seconds': row['elapsed_seconds'],
                          'inventory_id': next(n for n, name in names.items() if name == row['name']), 'name': row['name']})
    require(not pending, 'unreturned tank header call')
    return {'status': 'PASS', 'pairs': pairs, 'both_vehicles': {r['inventory_id'] for r in pairs} == {1, 2},
            'localization': expected['vehicle_display_names']}


def native_hangar(rows, wire, expected, minimum):
    common = entry.native_hangar(rows, wire, expected, minimum)['checks']
    checks = {key: common[key] for key in COMMON_NATIVE_CHECKS}
    # Reuse the unaltered identity/resource callbacks, explicitly exclude its
    # single-vehicle tank-name/readiness verdicts. New branches above handle two.
    header = common['native_header_identity_resources']['methods']
    checks['native_header_identity_resources'] = ui.aggregate({k: v for k, v in header.items() if k != 'as_setTankNameS'})
    measured = garage_observations(rows, expected, minimum)
    checks['native_hangar_continuously_ready_before_tabs'] = measured['readiness']
    checks['native_tank_header'] = tank_header(rows, expected)
    return ui.aggregate(checks), measured['selection_cycle']


def vehicle_photos(rows, images, expected):
    shots = [r for r in rows if r['event'] == 'vehicle_screenshot_requested']
    if not shots:
        return missing('Passive native vehicle photographs absent')
    require(len(shots) <= 2, 'passive vehicle screenshot count bound')
    samples = [r for r in rows if r['event'] == 'native_hangar']
    observed, numbers = [], set()
    for shot in shots:
        number, index = shot.get('selected_inventory_id'), shot.get('observation_index')
        require(type(number) is int and number in expected['vehicles'] and number not in numbers
                and type(index) is int and shot.get('basename') == 'vehicle_%d' % number
                and shot.get('writer') == 'BigWorld.screenShot' and shot.get('selection_changed_by_observer') is False
                and shot.get('model_loaded') is True, 'passive native photograph identity/origin differs')
        numbers.add(number)
        matches = [r for r in samples if r.get('observation_index') == index]
        require(len(matches) == 1 and ready(matches[0], expected['vehicles'])
                and 0 <= shot['elapsed_seconds'] - matches[0]['elapsed_seconds'] <= 1,
                'vehicle photograph is not bound to its ready native observation')
        stable = []
        for candidate in samples:
            if candidate['elapsed_seconds'] > matches[0]['elapsed_seconds']:
                break
            if (not ready(candidate, expected['vehicles']) or candidate['selected_inventory_id'] != number
                    or (stable and candidate['elapsed_seconds'] - stable[-1]['elapsed_seconds'] > 3)):
                stable = []
            if ready(candidate, expected['vehicles']) and candidate['selected_inventory_id'] == number:
                stable.append(candidate)
        require(len(stable) >= 3 and stable[-1]['elapsed_seconds'] - stable[0]['elapsed_seconds'] >= 2,
                'photograph lacks two sampled seconds of the same ready model')
        same(shot.get('vehicle'), expected['vehicles'][number], 'photographed descriptor differs from grant')
        same(matches[0].get('vehicle'), shot['vehicle'], 'photograph/sample vehicle differs')
        candidates = [r for r in images if re.fullmatch('screenshots/vehicle_%d_[0-9]+[.]png' % number, r['file'])]
        require(len(candidates) == 1, 'native vehicle screenshot missing/ambiguous')
        require(Path(candidates[0]['path']).parent.resolve() == Path(shot['directory']).resolve(), 'photograph directory differs')
        observed.append({'inventory_id': number, 'observation_index': index, 'elapsed_seconds': shot['elapsed_seconds'],
                         'file': candidates[0]['file'], 'sha256': candidates[0]['sha256'], 'vehicle': shot['vehicle']})
    return {'status': 'PASS' if numbers == {1, 2} else 'NOT_RUN', 'photos': observed,
            'scope': 'Native file/observation binding only; pixels need separate visual review.'}


def garage_visual(install, trace_sha, photos):
    path = install / 'visual-review-garage.json'
    if not path.exists() or photos.get('status') == 'NOT_RUN':
        return missing('Both hash-bound vehicle PNGs and visual review are required')
    raw = read_limited(path, 32768)
    review = entry.json_data(raw)
    require(review.get('schema_version') == 1 and review.get('reviewer') == 'root_visual_inspection'
            and review.get('status') in ('PASS', 'FAIL') and review.get('trace_sha256') == trace_sha, 'garage visual review identity')
    attestation = review.get('human_attestation')
    require(type(attestation) is dict and attestation.get('source') == 'direct_user_message'
            and attestation.get('trace_sha256') == trace_sha and type(attestation.get('statement')) is str
            and 1 <= len(attestation['statement']) <= 2048 and type(attestation.get('actions')) is list
            and {'select_is7', 'return_to_ms1'} <= set(attestation['actions']) and len(attestation['actions']) <= 8,
            'two-vehicle manual actions lack specific human attestation')
    reviews = review.get('vehicle_reviews')
    require(type(reviews) is list and len(reviews) == 2 and {r.get('inventory_id') for r in reviews} == {1, 2}, 'both vehicle reviews required')
    for row in reviews:
        photo = next(r for r in photos['photos'] if r['inventory_id'] == row['inventory_id'])
        same(row.get('screenshot'), {'file': photo['file'], 'sha256': photo['sha256']}, 'vehicle review PNG/hash differs')
        require(row.get('observation_index') == photo['observation_index'] and row.get('trigger_source') == 'human_attested'
                and type(row.get('findings')) is dict and all(row['findings'].get(key) is True for key in
                    ('hangar_visible', 'vehicle_model_visible', 'correct_vehicle_name', 'player_identity_visible', 'resources_unchanged')),
                'vehicle visual findings/observation missing')
    return ui.result(review['status'] == 'PASS', review_sha256=digest(raw), vehicle_reviews=reviews)


def observed_profile_return(rows, expected, awards):
    if not awards.get('renders'):
        return missing('Original own ProfileAwards delivery absent')
    require(not any(r['event'].startswith('profile_scenario_') or r['event'] == 'diagnostic_open_profile' for r in rows),
            'normal garage run contains automatic Profile navigation')
    samples = [(i, r) for i, r in enumerate(rows) if r['event'] == 'native_hangar']
    fini = [i for i, r in enumerate(rows) if r['event'] == 'fini_enter']
    require(len(fini) == 1, 'normal garage lifecycle lacks unique fini')
    correlations = []
    for render in awards['renders']:
        if render['data']['status'] != 'PASS':
            continue
        profile = []
        for i, row in samples:
            views = row.get('views') or {}
            main, sub = views.get('main') or {}, views.get('lobby_sub') or {}
            if (render['return_seconds'] <= row['elapsed_seconds'] <= render['return_seconds'] + 3 and i < fini[0]
                    and main.get('class_name') == 'LobbyView' and main.get('flash_bound') is True
                    and sub.get('class_name') == 'ProfilePage' and sub.get('alias') == 'profile' and sub.get('flash_bound') is True
                    and row.get('native_connected') is True and row.get('items_cache_synced') is True
                    and row.get('waiting_visible') is False and row.get('resources') == expected['resources']
                    and row.get('statistics') == expected['profile']['statistics']):
                profile.append((i, row))
        before = [(i, r) for i, r in samples if r['elapsed_seconds'] < render['call_seconds'] and ready(r, expected['vehicles'])]
        after = [(i, r) for i, r in samples if profile and profile[0][0] < i < fini[0] and ready(r, expected['vehicles'])]
        if before and profile and after:
            correlations.append({'awards_call_id': render['call_id'], 'owner_id': render['owner_id'],
                                 'hangar_before_line': before[-1][0] + 1, 'profile_line': profile[0][0] + 1,
                                 'hangar_return_line': after[0][0] + 1, 'returned_inventory_id': after[0][1]['selected_inventory_id']})
    return {'status': 'PASS' if correlations else 'NOT_RUN', 'observations': correlations}


def gui_visual_review(rows, install, images, trace_sha, tooltip, awards):
    """Schema2 records partial visual coverage without inventing positive pixels.

    The old all-or-nothing schema1 validator is left unchanged. A missed delayed
    tooltip capture is an observed lack of visual proof, not a successful tooltip
    image and not a suppression of any original callback/runtime failure.
    """
    path = install / 'visual-review-ui.json'
    if not path.exists():
        return missing('Actual tooltip and Awards PNG review absent')
    raw = read_limited(path, 32768)
    review = entry.json_data(raw)
    if review.get('schema_version') == 1:
        return ui.gui_visual_review(install, images, trace_sha, tooltip, awards, require_human_actions=True)
    require(review.get('schema_version') == 2 and review.get('reviewer') == 'root_visual_inspection'
            and review.get('trace_sha256') == trace_sha and review.get('status') in ('PASS', 'FAIL', 'NOT_RUN'),
            'partial GUI visual review schema/trace identity')
    attestation = review.get('human_attestation')
    require(type(attestation) is dict and attestation.get('source') == 'direct_user_message'
            and attestation.get('trace_sha256') == trace_sha and type(attestation.get('statement')) is str
            and 1 <= len(attestation['statement']) <= 2048 and type(attestation.get('actions')) is list
            and len(attestation['actions']) <= 8, 'partial GUI visual review lacks direct human attestation')
    actions = set(attestation['actions'])

    def image_for(item, kind):
        call_id, screenshot = item.get('call_id'), item.get('screenshot')
        require(type(call_id) is int and type(screenshot) is dict, 'partial GUI image/call shape')
        matched = [r for r in images if r['file'] == screenshot.get('file') and r['sha256'] == screenshot.get('sha256')]
        markers = [r for r in rows if r['event'] == kind and r.get('call_id') == call_id]
        require(len(matched) == len(markers) == 1 and markers[0].get('writer') == 'BigWorld.screenShot'
                and markers[0].get('original_hover_unchanged') is True, 'GUI image lacks its exact native passive marker')
        photo, marker = matched[0], markers[0]
        require(type(marker.get('basename')) is str and re.fullmatch(
                re.escape('screenshots/' + marker['basename']) + r'_[0-9]+[.]png', photo['file'])
                and Path(photo['path']).parent.resolve() == Path(marker['directory']).resolve(), 'GUI photo path/marker mismatch')
        return {'call_id': call_id, 'screenshot': screenshot, 'capture_seconds': marker['elapsed_seconds']}

    checks, positive_ids = {}, set()
    definitions = (
        ('tooltip_reviews', 'tooltip_visual', tooltip.get('displays', []), 'tooltip_screenshot_requested',
         ('tooltip_visible', 'matches_target', 'text_readable'), {'hover_tooltip'}),
        ('awards_reviews', 'awards_visual', awards.get('renders', []), 'profile_screenshot_requested',
         ('awards_tab_visible', 'native_catalog_visible', 'player_identity_visible'), {'open_awards', 'return_to_hangar'}))
    for field, check, callbacks, kind, flags, required_actions in definitions:
        values = review.get(field)
        require(type(values) is list and len(values) <= 8, 'partial GUI review array bound')
        images_reviewed, seen = [], set()
        for value in values:
            proof = image_for(value, kind)
            number = proof['call_id']
            require(number not in seen and any(r['call_id'] == number for r in callbacks), 'visual review lacks verified original callback')
            require(value.get('trigger_source') == 'human_attested' and required_actions <= actions,
                    'partial GUI visual review lacks actual relevant human actions')
            seen.add(number)
            findings = value.get('findings')
            require(type(findings) is dict and all(type(findings.get(flag)) is bool for flag in flags), 'visual findings must be explicit booleans')
            proof.update(findings=findings, status='PASS' if all(findings[flag] for flag in flags) else 'FAIL')
            images_reviewed.append(proof)
        if field == 'tooltip_reviews':
            positive_ids = seen
        checks[check] = (ui.aggregate({str(r['call_id']): r for r in images_reviewed}) if images_reviewed
                         else missing('Required native image has not been visually confirmed'))
    misses = review.get('tooltip_capture_misses', [])
    require(type(misses) is list and len(misses) <= 8, 'tooltip capture-miss bound')
    observed, seen = [], set()
    for item in misses:
        require(item.get('finding') == 'tooltip_not_visible_at_capture' and 'hover_tooltip' in actions,
                'unmeasured tooltip capture miss/physical action')
        proof = image_for(item, 'tooltip_screenshot_requested')
        require(proof['call_id'] not in seen | positive_ids, 'duplicate or contradictory tooltip visual record')
        seen.add(proof['call_id'])
        observed.append({**proof, 'finding': item['finding']})
    result = ui.aggregate(checks)
    require(review['status'] == result['status'], 'partial GUI declared status contradicts measured visual coverage')
    return {**result, 'review_sha256': digest(raw), 'observed_capture_misses': observed,
            'scope': 'Individual pixel findings retained; absent delayed tooltip pixels remain NOT_RUN. Original callback/runtime errors are checked separately and cannot be masked.'}


def gui_evidence(rows, expected, images, install, trace_sha):
    contracts, sources = ui.original_ui_contracts()
    checks = {'original_bytecode': sources}
    checks['tooltip_callbacks'] = checked(lambda: ui.tooltip_evidence(rows, contracts))
    checks['awards_callbacks'] = checked(lambda: ui.awards_evidence(rows, contracts, expected))
    checks['observed_profile_return'] = checked(lambda: observed_profile_return(rows, expected, checks['awards_callbacks']))
    checks['gui_visual_review'] = checked(lambda: gui_visual_review(rows, install, images, trace_sha,
                checks['tooltip_callbacks'], checks['awards_callbacks']))
    return ui.aggregate(checks)


def identity_snapshot(expected, identity):
    return {'account_id': expected['account_id'], 'native_database_id': expected['native_id'], 'nickname': expected['name'],
            'snapshot_revision': 2, 'catalog_revision': 3, 'wire_sync_revision': 1,
            'fixture_manifest_sha256': expected['manifest_sha256'], 'profile_sha256': identity['profile_sha256'],
            'base_profile_sha256': identity['base_profile_sha256'], 'compatibility_sha256': identity['compatibility_sha256'],
            'fixture_files': {name: {'sha256': digest(raw), 'bytes': len(raw)} for name, raw in expected['raw'].items()},
            'resources': expected['resources'], 'statistics': expected['profile']['statistics'],
            'vehicles': {str(key): value for key, value in expected['vehicles'].items()},
            'dossier_cache': expected['dossier_cache']}


def session_status(report):
    return entry.status_checks({**report.get('checks', {}), **{key: report.get(key, missing('not captured'))
                 for key in ('wire', 'backend', 'native_common', 'native_hangar', 'visual')}})


def cache_hint_backend(backend, wire):
    """Correlate initial full streams and the same-hash no-change refresh."""
    path = Path(backend['source'])
    raw = read_limited(path, 8 * 1024 * 1024)
    require(backend.get('source_is_frozen_span') is True and digest(raw) == backend.get('source_sha256'),
            'cache hint backend requires unchanged frozen gateway span')
    text, session = raw.decode('utf8'), backend['session_id']
    records = re.findall(rf'^INITIAL_CACHE_HINT session={session} request=(\d+) command=(\d+) '
                         r'descriptor_a=(-?\d+) descriptor_b=(-?\d+) response=full_stream client_state_applied=false$', text, re.M)
    expected = {}
    for command in wire['commands']:
        if command['kind'] != 'sync':
            continue
        if command['command'] == 100 and command.get('persistent_crc', 0) != 0:
            expected[command['request']] = (100, command['persistent_crc'], 0)
        elif command['command'] == 300 and command.get('cached_bytes', 0) != 0:
            expected[command['request']] = (300, command['cached_bytes'], command['cached_crc32_signed'])
    require(len(records) == len(expected) and {int(q): (int(c), int(a), int(b)) for q, c, a, b in records} == expected,
            'server advisory cache handling differs from native request metadata')
    refresh_records = re.findall(rf'^REFRESH_CACHE_HINT session={session} request=(\d+) '
                                r'descriptor_a=(-?\d+) descriptor_b=0 response=no_change client_state_applied=false$', text, re.M)
    refresh_expected = {row['request']: row['persistent_crc'] for row in wire['commands']
                        if row['kind'] == 'refresh' and row.get('persistent_crc', 0) != 0}
    require(len(refresh_records) == len(refresh_expected)
            and {int(q): int(a) for q, a in refresh_records} == refresh_expected,
            'server cached refresh handling differs from native request metadata')
    return {'status': 'PASS', 'requests': [{'request': key, 'command': value[0], 'descriptor_a': value[1],
              'descriptor_b': value[2]} for key, value in expected.items()],
            'refresh_requests': [{'request': key, 'descriptor_a': value, 'descriptor_b': 0}
                                 for key, value in refresh_expected.items()],
            'scope': 'Initial descriptors are advisory and require exact full authenticated fixture streams. '
                     'Refresh repeats the same initial descriptor and requires the original no-change response; '
                     'no client cache state is applied.'}


def relogin(previous_path, report, local_root):
    if previous_path is None:
        return missing('A second actual clean client process is required to prove relogin and cached CMD600')
    path = entry.owned(previous_path, local_root)
    raw = read_limited(path, 8 * 1024 * 1024)
    previous = entry.json_data(raw)
    require(previous.get('schema_version') == SCHEMA and previous.get('tool') == TOOL, 'unknown previous garage verifier schema')
    require(previous.get('install') != report['install'], 'same installation run cannot prove relogin')
    old_install = entry.owned(previous['install'], local_root, True)
    require(digest(local_file(old_install, 'install-plan.json', 256 * 1024)) == previous['checks']['installation_plan']['sha256'],
            'previous installation evidence changed')
    trace = entry.owned(previous['native_common']['trace']['path'], local_root)
    require(digest(read_limited(trace, 17 * 1024 * 1024)) == previous['native_common']['trace']['sha256']
            and digest(local_file(old_install, 'wire/capture.json', 8 * 1024 * 1024)) == previous['wire']['capture_sha256'],
            'previous trace or raw wire capture changed')
    previous_capture = entry.json_data(local_file(old_install, 'wire/capture.json', 8 * 1024 * 1024))
    packets = previous_capture.get('packets')
    require(type(packets) is list and 1 <= len(packets) <= entry.MAX_PACKETS, 'previous packet corpus bound')
    packet_bytes = 0
    for packet in packets:
        packet_raw = local_file(old_install / 'wire', packet['file'], 4096)
        packet_bytes += len(packet_raw)
        require(packet_bytes <= 16 * 1024 * 1024 and len(packet_raw) == packet.get('bytes')
                and digest(packet_raw) == packet.get('sha256'), 'previous packet evidence changed')
    require(previous.get('session_status') == report.get('session_status') == 'PASS'
            and session_status(previous) == session_status(report) == 'PASS', 'two clean native sessions required')
    same(previous.get('identity_snapshot'), report.get('identity_snapshot'), 'relogin changed immutable account/inventory/resources')
    require(ui.compiled_snapshot(previous) == ui.compiled_snapshot(report), 'relogin source/bytecode package differs')
    start, finish = datetime.fromisoformat(report['process']['started_utc']), datetime.fromisoformat(previous['process']['finished_utc'])
    require(start.tzinfo is not None and finish.tzinfo is not None and start >= finish, 'client process windows overlap')
    require(previous['wire']['capture_sha256'] != report['wire']['capture_sha256'], 'reused wire corpus is not a new login')
    if previous['process']['gateway_run'] == report['process']['gateway_run']:
        require(previous['backend']['session_id'] != report['backend']['session_id'], 'same gateway session reused')
    old_plan = entry.json_data(local_file(old_install, 'install-plan.json', 256 * 1024))
    current_plan = entry.json_data(local_file(Path(report['install']), 'install-plan.json', 256 * 1024))
    require(Path(old_plan['settings']['profile_dir']).resolve() == Path(current_plan['settings']['profile_dir']).resolve(),
            'relogin did not reuse the same native cache directory')
    policy = report['identity_snapshot']['dossier_cache']
    requests = [r for r in report['wire']['commands'] if r.get('command') == 600]
    require(len(requests) == 1 and requests[0].get('revision') == policy['version']
            and requests[0].get('last_change_time') == policy['last_change_time'], 'second native login did not send the exact persisted IS-7 dossier cursor')
    return {'status': 'PASS', 'previous_report': str(path), 'previous_report_sha256': digest(raw),
            'dossier_cache': policy, 'native_cache_directory_equal': True, 'compiled_sources_equal': True,
            'scope': 'Independent clean native login and exact server-owned cached600; identity/profile/payload hashes unchanged.'}


def paired_coverage(kind, report, previous_path, local_root):
    current = report[kind]
    if current['status'] in ('PASS', 'FAIL'):
        return {'status': current['status'], 'coverage': 'current_run'}
    if previous_path is None or report['relogin']['status'] != 'PASS':
        return missing('No complete current coverage or clean paired predecessor')
    path = entry.owned(previous_path, local_root)
    raw = read_limited(path, 8 * 1024 * 1024)
    require(digest(raw) == report['relogin']['previous_report_sha256'], 'paired report changed during verification')
    previous = entry.json_data(raw)
    require(ui.compiled_snapshot(previous) == ui.compiled_snapshot(report), 'paired coverage sources differ')
    same(previous['identity_snapshot'], report['identity_snapshot'], 'paired coverage identity differs')
    if previous.get(kind, {}).get('status') != 'PASS':
        return missing('Previous paired run did not complete ' + kind)
    return {'status': 'PASS', 'coverage': 'previous_paired_run', 'previous_report': str(path), 'previous_report_sha256': digest(raw)}


def verify(args):
    local_root = config()[1]['local_artifacts_root']
    report = {'schema_version': SCHEMA, 'tool': TOOL, 'status': 'NOT_RUN', 'session_status': 'NOT_RUN',
              'scope': 'Explicit MS-1 + IS-7 server test grant; native normal entry/render/exit/relogin. No combat/economy.',
              'mode': args.mode, 'case': args.case, 'checks': {}}
    for key in ('wire', 'backend', 'native_common', 'native_hangar', 'visual', 'garage', 'gui', 'relogin', 'card_garage', 'card_gui'):
        report[key] = missing('not evaluated')
    stage = 'inputs'
    try:
        require(args.mode == 'normal', 'test garage acceptance requires normal human entry')
        install = entry.owned(args.install, local_root, True)
        report['install'] = str(install)
        base = entry.owned(args.base_fixture, local_root, True)
        fixture = entry.owned(args.fixture, local_root, True)
        require(base != fixture and base.name == 'r1-catalog2', 'separate immutable historical base fixture required')
        expected, password, identity = ui.catalog_identity_inputs(entry.owned(args.registration, local_root),
                entry.owned(args.credentials, local_root), args.case, base, base.parent / 'r1')
        identity.pop('email', None)
        report['checks']['website_base_identity'] = identity
        expected, fixture_report = garage_fixture(fixture, base, expected, local_root)
        report['checks']['garage_fixture'] = fixture_report
        report['identity_snapshot'] = identity_snapshot(expected, fixture_report)
        plan_raw = local_file(install, 'install-plan.json', 256 * 1024)
        plan = entry.json_data(plan_raw)
        outcome = entry.read_json(install / 'native-outcome.json', 65536)
        require(outcome.get('plan_sha256') == digest(plan_raw), 'native outcome/install plan mismatch')
        same(entry.json_data(local_file(install, 'postrun/sr_interactive_settings.json', 16384)), plan['settings'], 'runtime settings changed')
        require(plan['settings'].get('capture_ui_passive') is True and plan['settings'].get('capture_hangar') is True,
                'normal native run lacks prepared passive screenshots')
        report['checks']['installation_plan'] = {'status': 'PASS', 'sha256': digest(plan_raw)}
        report['process'] = {k: outcome.get(k) for k in ('client_pid', 'started_utc', 'finished_utc', 'gateway_run')}
        run = entry.owned(outcome['gateway_run'], local_root, True)
        expected_digest = read_limited(run.parent / 'client-digest.bin', 16)
        require(len(expected_digest) == 16, 'client digest size')
        stage = 'native_common'
        rows, trace_info = entry.runtime_rows(install, plan, outcome, local_root)
        report[stage] = ui.native_common(install, plan, outcome, rows, trace_info, args.mode)
        stage = 'wire'
        report[stage] = entry.wire(install, entry.owned(args.private_key, local_root), expected, password,
                                 expected_digest, dossier_cache=expected['dossier_cache'], cache_hints=True)
        del password
        stage = 'backend'
        report[stage] = entry.backend_binding(install, outcome, report['wire'], expected, local_root)
        report[stage]['cache_hint_handling'] = cache_hint_backend(report[stage], report['wire'])
        stage = 'native_hangar'
        report[stage], selection = native_hangar(rows, report['wire'], expected, args.min_ready_seconds)
        stage = 'visual'
        images = ui.screenshot_images(install, plan, local_root)
        report[stage] = {**ui.hangar_visual(install, images), 'screenshots': images}
        stage = 'garage'
        photos = checked(lambda: vehicle_photos(rows, images, expected))
        header = report['native_hangar']['checks']['native_tank_header']
        both_names = {'status': 'PASS'} if header.get('both_vehicles') is True else missing('Both native localized tank header names were not observed')
        report[stage] = ui.aggregate({'selection_cycle': selection, 'both_native_header_names': both_names,
            'passive_photos': photos, 'visual_review': checked(lambda: garage_visual(install, trace_info['sha256'], photos))})
        stage = 'gui'
        report[stage] = gui_evidence(rows, expected, images, install, trace_info['sha256'])
        report['session_status'] = session_status(report)
        stage = 'relogin'
        report[stage] = relogin(args.previous_report, report, local_root)
        for kind in ('garage', 'gui'):
            stage = 'card_' + kind
            report[stage] = paired_coverage(kind, report, args.previous_report, local_root)
    except FileNotFoundError as error:
        if stage in report:
            report[stage] = missing(str(error))
        else:
            report['checks'][stage] = missing(str(error))
    except ui.FAILURES as error:
        failure = {'status': 'FAIL', 'error_type': type(error).__name__, 'error': str(error)}
        if stage in report:
            report[stage] = failure
        else:
            report['checks'][stage] = failure
    for kind in ('garage', 'gui'):
        if report[kind]['status'] == 'FAIL':
            report['card_' + kind] = {'status': 'FAIL', 'coverage': 'current_run', 'reason': 'Current measured failure cannot be replaced by earlier coverage'}
    report['session_status'] = session_status(report)
    report['status'] = entry.status_checks({'session': {'status': report['session_status']},
        **{key: report[key] for key in ('card_garage', 'card_gui', 'relogin')}})
    report['verifier_sources'] = [{'file': str(ROOT / 'tools' / name), 'sha256': digest(read_limited(ROOT / 'tools' / name, 256 * 1024))}
        for name in ('verify_test_garage.py', 'verify_hangar_ui.py', 'verify_unified_entry.py', 'verify_hangar.py',
                     'verify_redirect_capture.py', 'verify_baseapp_capture.py', 'verify_channel_capture.py', 'py27_static.py', 'packed_xml.py')]
    report['limitations'] = ['Generated/synthetic unit inputs are not native compatibility evidence.',
        'Physical actions require direct user attestation, pixels require root inspection of the hash-bound native PNG.',
        'Issued vehicles have no crew or ammunition and are not battle ready. Prices are original display references, not trade support.',
        'No arena, combat, economic actions, general GUI coverage or nonlocal service is accepted by this report.']
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('install', 'registration', 'credentials', 'case', 'fixture', 'base-fixture', 'private-key', 'out'):
        parser.add_argument('--' + name, required=True)
    parser.add_argument('--mode', choices=('normal',), default='normal')
    parser.add_argument('--min-ready-seconds', type=float, default=60)
    parser.add_argument('--previous-report')
    args = parser.parse_args()
    require(60 <= args.min_ready_seconds <= 1800, 'minimum acceptance duration cannot be less than 60 seconds')
    out = output_dir(args.out)
    report = verify(args)
    save_json(out / 'test-garage-verification.json', report)
    print(entry.json.dumps({'status': report['status'], 'session_status': report['session_status'], 'out': str(out)}))
    raise SystemExit(0 if report['status'] == 'PASS' else 1)


if __name__ == '__main__':
    main()
