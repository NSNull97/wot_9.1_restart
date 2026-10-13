"""P04B bounded, read-only #717 crew/optional-device source verification.

This is a source receipt, not a native installation or combat compatibility
test. The installed-device subset is project policy; other source devices are
unsupported by this card. Original bytecode is inspected as data, never run.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

if __package__:
    from .destructible_catalog import CatalogError, json_value, no_links, read, string
    from .packed_xml import decode, walk
    from .py27_static import inspect, opcode_table
else:
    from destructible_catalog import CatalogError, json_value, no_links, read, string
    from packed_xml import decode, walk
    from py27_static import inspect, opcode_table


SCHEMA_VERSION = 1
SOURCE_BUILD = 'v.0.9.1 #717'
SOURCE_MANIFEST = '74c37c18e9ac7e30196c134076dacf6f2a8bf3897f7def73905d09feb3647797'
ROOT = Path(__file__).resolve().parents[1]
OPCODE_PIN = (5474, 'acfe212847ecb81ca28bdab976a3caacff3568b45a9e8ca78d6957f9f3ef4884')
# Exact private resource bytes remain local. Paths are relative to res/scripts.
SOURCE_PINS = {
    'common/items/vehicles.pyc': (125668, '805240e4b59d8a75950dbb97b41c17867606e7e96d7ff0c8d7b05312b83ae8b6'),
    'common/items/artefacts.pyc': (18972, 'aedbfc161d7f0b2b78f376540811a0b4113736757982d03bceb4e6f4cccac49c'),
    'common/items/__init__.pyc': (4303, '587ba137fee1b7de77ce81d5e963185ba20267c54d157ce8699a76f2f0d11176'),
    'common/items/_xml.pyc': (5826, '86d408fa983b6a74c7475930f5e651253fe0135dbde22467b30e9cee4224cf1b'),
    'common/nations.pyc': (565, '34392915b0d2a70a3df0b8151e0fdbb9cb58aad6a708ffc85843c45c596a4562'),
    'common/items/tankmen.pyc': (24558, '74f914b1e5e7e574086dd865d87e4cfbf8cace6e60b5e506757eba28ca8bc530'),
    'client/gui/shared/gui_items/vehicle.pyc': (25863, 'ec78e36ab100e2c2274dd69476da99a26791037c6d79d707921168b1e95ae1e8'),
    'client/gui/shared/gui_items/tankman.pyc': (15745, '07645906b7cac95bc482c0e9548b37c598d3ec440752f7f19058688f981fa364'),
    'item_defs/vehicles/common/optional_devices.xml': (14807, 'f24f01573b3848df1a5051752a2e5f937857e7062b78a4dd1812194486c843c6'),
    'item_defs/vehicles/ussr/list.xml': (18228, '167a637d725a233d42e52bd7d5bac00b9af45c0ef225163ab578e202454f5138'),
    'item_defs/vehicles/ussr/ms-1.xml': (11839, 'a494bf04d29da7d066fd6923dbb75a79b947559a52405298c494a943c4b0c535'),
    'item_defs/vehicles/ussr/is-7.xml': (5809, '8d55fa4657a88f1436cd164afe11bade875a906fa7b97256f1fb2f803b09c10d'),
}
DEVICE_POLICY = {
    5: ('coatedOptics', 'StaticFactorDevice', 'circularVisionRadiusFactor', '1.1', 0, (), ()),
    17: ('improvedVentilation_class1', 'StaticAdditiveDevice', 'crewLevelIncrease', '5', 100,
         ('lightTank', 'improvedVentilation_class1_user'), ('noImprovedVentilation',)),
    19: ('improvedVentilation_class3', 'StaticAdditiveDevice', 'crewLevelIncrease', '5', 200,
         ('heavyTank', 'heavyAT-SPG', 'improvedVentilation_class3_user'), ('noImprovedVentilation',)),
    25: ('enhancedAimDrives', 'StaticFactorDevice', 'gunAimingTimeFactor', '0.91', 100, (), ()),
}
ROSTERS = {
    'MS-1': (('commander', 'gunner', 'radioman', 'loader'), ('driver',)),
    'IS-7': (('commander',), ('gunner',), ('driver',), ('loader',), ('loader', 'radioman')),
}
VEHICLE_IDS = {'MS-1': 13, 'IS-7': 28}
VEHICLE_TAGS = {
    'MS-1': ('lightTank',),
    'IS-7': ('heavyTank', 'sinai', 'enhancedTorsions5t_user', 'largeCaliberTankRammer_user',
             'wetCombatPack_class2_user', 'aimingStabilizer_Mk2_user'),
}


class SourceAuditError(ValueError):
    """Source provenance or the admitted static boundary did not match."""


def require(condition, message):
    if not condition:
        raise SourceAuditError(message)


def pinned_read(path, pin):
    size, sha256 = pin
    raw = read(path, size, sha256)
    require(len(raw) == size, f'source size mismatch: {path}')
    return raw


def device_policy(device_id):
    require(type(device_id) is int and device_id in DEVICE_POLICY, 'unsupported optional device')
    return DEVICE_POLICY[device_id]


def _scalar(value):
    if type(value) is dict and set(value) == {'value', 'children'}:
        value = value['value']
    # Reuse the established PackedSection kind5 textual interpretation.
    return string(value) if type(value) in (str, dict) else value


def extract_xml_facts(raw_sources):
    devices = dict(walk(decode(raw_sources['item_defs/vehicles/common/optional_devices.xml'])))
    result = []
    for device_id in DEVICE_POLICY:
        name, script, attr, amount, weight, include, exclude = device_policy(device_id)
        prefix = '/' + name + '[1]'
        def value(suffix, default=None):
            return _scalar(devices.get(prefix + suffix, default))
        require(value('/id[1]') == device_id, f'wrong device id: {name}')
        require(value('/script[1]') == script, f'wrong script: {name}')
        require(value('/script[1]/attribute[1]') == 'miscAttrs/' + attr, f'wrong attribute: {name}')
        key = 'value' if script == 'StaticAdditiveDevice' else 'factor'
        require(str(value('/script[1]/' + key + '[1]')) == amount, f'wrong coefficient: {name}')
        require(value('/script[1]/weight[1]', 0) == weight, f'wrong mass: {name}')
        require(value('/script[1]/vehicleWeightFraction[1]', 0) == 0, 'unsupported mass fraction')
        for which, expected in [('include', include), ('exclude', exclude)]:
            actual = value('/vehicleFilter[1]/' + which + '[1]/vehicle[1]/tags[1]', '')
            require(tuple(actual.split()) == expected, f'wrong {which} tags: {name}')
        result.append({'source_name': name, 'source_id': device_id,
                       'native_compact_id': device_id * 256 + 249,
                       'script': script, 'attribute': 'miscAttrs/' + attr,
                       'decimal_literal': amount, 'weight_kg': weight,
                       'include_any_tags': list(include), 'exclude_any_tags': list(exclude)})
    vehicle_list = dict(walk(decode(raw_sources['item_defs/vehicles/ussr/list.xml'])))
    vehicles = []
    for name, expected_roles in ROSTERS.items():
        source = 'item_defs/vehicles/ussr/' + name.lower() + '.xml'
        tree = decode(raw_sources[source])
        crews = [child['data'] for child in tree['children'] if child['name'] == 'crew']
        require(len(crews) == 1, 'crew section count')
        roles = tuple((child['name'], *_scalar(child['data']).split()) for child in crews[0]['children'])
        require(roles == expected_roles, f'wrong crew order/roles: {name}')
        prefix = '/' + name + '[1]'
        require(vehicle_list[prefix + '/id[1]'] == VEHICLE_IDS[name], 'wrong vehicle id')
        tags = tuple(_scalar(vehicle_list[prefix + '/tags[1]']).split())
        require(tags == VEHICLE_TAGS[name], 'wrong vehicle tags')
        vehicles.append({'source_name': 'ussr:' + name, 'nation_id': 0,
                         'source_id': VEHICLE_IDS[name],
                         'type_compact_id': VEHICLE_IDS[name] * 256 + 1,
                         'roles_by_slot': [list(row) for row in roles], 'tags': list(tags)})
    return {'vehicles': vehicles, 'optional_devices': result}


def verify_bytecode(raw_sources, table):
    facts = []
    cache = {}
    def record(source, name):
        if source not in cache:
            cache[source] = {r['qualified_name']: r for r in inspect(raw_sources[source], table)}
        key = '<module>' if name == '<module>' else '<module>.' + name
        require(key in cache[source], f'missing static record: {key}')
        return cache[source][key]
    def expect(source, name, offset, opname, value):
        row = record(source, name)
        matched = [i for i in row['instructions'] if i['offset'] == offset]
        require(len(matched) == 1 and matched[0]['opname'] == opname
                and matched[0].get('value', matched[0].get('arg')) == value,
                f'bytecode assertion differs: {name}:{offset}')
        facts.append({'source': source, 'record': row['qualified_name'],
                      'source_line': row['firstlineno'], 'offset': offset,
                      'opname': opname, 'value': value})
    vehicles = 'common/items/vehicles.pyc'
    artefacts = 'common/items/artefacts.pyc'
    expect(vehicles, '<module>', 540, 'LOAD_CONST', 3)
    expect(vehicles, '<module>', 543, 'STORE_NAME', 'NUM_OPTIONAL_DEVICE_SLOTS')
    expect(vehicles, '<module>', 549, 'STORE_NAME', 'NUM_EQUIPMENT_SLOTS')
    expect('common/nations.pyc', '<module>', 40, 'LOAD_CONST', 15)
    expect('common/nations.pyc', '<module>', 43, 'STORE_NAME', 'NONE_INDEX')
    item_names = record('common/items/__init__.pyc', '<module>')['instructions']
    items = next(i['value'] for i in item_names if i['offset'] == 91)
    require(items.index('optionalDevice') == 9 and items.index('equipment') == 11, 'native item categories')
    expect(vehicles, 'makeIntCompactDescrByID', 13, 'LOAD_CONST', 4)
    expect(vehicles, 'makeIntCompactDescrByID', 24, 'LOAD_CONST', 8)
    expect(vehicles, 'VehicleDescr.__updateAttributes', 599, 'LOAD_CONST', 'crewLevelIncrease')
    expect(vehicles, 'VehicleDescr.__updateAttributes', 622, 'LOAD_ATTR', 'optionalDevices')
    expect(vehicles, 'VehicleDescr.__updateAttributes', 647, 'LOAD_ATTR', 'updateVehicleDescrAttrs')
    expect(vehicles, 'VehicleDescr.mayInstallOptionalDevice', 90, 'LOAD_CONST', 'already installed')
    expect(vehicles, 'VehicleDescr.mayInstallOptionalDevice', 204, 'LOAD_GLOBAL', '_isWeightAllowedToChange')
    expect(artefacts, '_VehicleFilter.checkCompatibility', 3, 'LOAD_ATTR', '_VehicleFilter__exclude')
    expect(artefacts, '_VehicleFilter.checkCompatibility', 61, 'LOAD_ATTR', '_VehicleFilter__include')
    expect(artefacts, '_matchSubfilter', 155, 'LOAD_ATTR', 'intersection')
    expect(artefacts, 'StaticFactorDevice.updateVehicleDescrAttrs', 121, 'BINARY_MULTIPLY', None)
    expect(artefacts, 'StaticFactorDevice.updateVehicleDescrAttrs', 144, 'BINARY_MULTIPLY', None)
    expect(artefacts, 'StaticAdditiveDevice.updateVehicleDescrAttrs', 121, 'BINARY_ADD', None)
    expect(artefacts, 'StaticAdditiveDevice.updateVehicleDescrAttrs', 144, 'BINARY_ADD', None)
    expect('common/items/_xml.pyc', 'readPositiveFloat', 3, 'LOAD_ATTR', 'readFloat')
    return facts


def audit(config_path):
    config_path = no_links(config_path)
    config = json_value(read(config_path, 65536).removeprefix(b'\xef\xbb\xbf'), depth=12, nodes=1024)
    require(config.get('target', {}).get('exact_build') == SOURCE_BUILD, 'unexpected client build')
    require(config['target'].get('client_manifest_sha256') == SOURCE_MANIFEST, 'unexpected client manifest')
    paths = config.get('paths', {})
    for key in ('original_client_root', 'local_artifacts_root'):
        require(type(paths.get(key)) is str and Path(paths[key]).is_absolute(), 'configured absolute root required')
    original = no_links(paths['original_client_root']).resolve(strict=True)
    local = no_links(paths['local_artifacts_root']).resolve(strict=True)
    raw_sources = {name: pinned_read(original / 'res/scripts' / name, pin)
                   for name, pin in SOURCE_PINS.items()}
    opcode = pinned_read(local / 'vendor/cpython-2.7.3/opcode.py', OPCODE_PIN)
    facts = extract_xml_facts(raw_sources)
    bytecode = verify_bytecode(raw_sources, opcode_table(opcode.decode('utf-8')))
    return {'schema_version': SCHEMA_VERSION, 'status': 'PASS_P04B_STATIC_SOURCE_AUDIT',
            'classification': 'VERIFIED_STATIC', 'build': SOURCE_BUILD,
            'client_manifest_sha256': SOURCE_MANIFEST,
            'sources': [{'source_id': 'res/scripts/' + name, 'bytes': pin[0], 'sha256': pin[1]}
                        for name, pin in sorted(SOURCE_PINS.items())],
            'opcode_table': {'bytes': OPCODE_PIN[0], 'sha256': OPCODE_PIN[1]},
            'facts': facts, 'bytecode_assertions': bytecode,
            'optional_device_slots': 3, 'native_optional_device_category': 9,
            'native_consumable_equipment_category': 11, 'optional_device_nation_id': 15,
            'modifier_order': 'initialize neutral miscAttrs; apply nonempty optional devices in slot order',
            'compatibility': 'reject duplicate; exclude matches before include; listed tags use any intersection; mass gate',
            'native_weight_formula': 'base_mass*(1+sum(fraction))+sum(addition); limit=chassis.maxLoad+sum(limit_change)',
            'native_weight_change_gate': 'new_reserve>=0 or new_reserve>=old_reserve',
            'arithmetic_boundary': 'source decimal literals VERIFIED; native readFloat binary representation UNKNOWN; project rational snapshot is not bit-exact native arithmetic',
            'not_run': ['native device installation', 'live IS-7 crew assignment', 'runtime wiring',
                        'final combat characteristics', 'native binary32 coefficient readback'],
            'no_client_code_executed': True, 'no_database_or_service_access': True}


def write_receipt(report, out, repository=ROOT):
    repository = no_links(repository).resolve(strict=True)
    require(repository.is_dir(), 'repository must be an existing directory')
    local = no_links(repository / 'local').resolve()
    out = no_links(out).resolve()
    require(out.is_relative_to(local) and out != local, 'output must be within this worktree local/')
    require(not out.exists(), 'fresh evidence directory required')
    local.mkdir(exist_ok=True)
    out.mkdir(parents=True)
    data = (json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + '\n').encode('utf-8')
    path = out / 'receipt.json'
    with path.open('xb') as stream:
        stream.write(data)
    return {'status': report['status'], 'receipt': str(path), 'sha256': hashlib.sha256(data).hexdigest()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True, help='explicit authorized local configuration (read-only)')
    parser.add_argument('--out', type=Path, required=True, help='fresh directory under this worktree local/')
    args = parser.parse_args()
    try:
        result = write_receipt(audit(args.config), args.out)
    except (SourceAuditError, CatalogError, OSError, KeyError, TypeError, ValueError) as error:
        parser.exit(1, f'FAIL_P04B_STATIC_SOURCE_AUDIT: {error}\n')
    print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    main()
