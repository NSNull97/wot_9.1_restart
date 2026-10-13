"""Bounded read-only #717 native maintenance source audit; never executes pyc."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

if __package__:
    from .destructible_catalog import no_links, read
    from .p09c_ammo_catalog import audit_sources as audit_catalog
    from .packed_xml import decode
    from .py27_static import inspect, opcode_table, parse_pyc, records, text
else:
    from destructible_catalog import no_links, read
    from p09c_ammo_catalog import audit_sources as audit_catalog
    from packed_xml import decode
    from py27_static import inspect, opcode_table, parse_pyc, records, text

ROOT = Path(__file__).resolve().parents[1]
PREFIX = 'res/scripts/'
PINS = {
    'client/Account.pyc': (45998, 'bb6e88e4aec03161212847ffc3601d16917610b8f7815c42f91f610693f4d0ef'),
    'client/account_helpers/Inventory.pyc': (22611, '3d17842cc6fa9af05d53cc6d22dc286e6b0434356e58c6f74d5822c2dd3cbf19'),
    'client/account_helpers/AccountSyncData.pyc': (6770, '8032c14629301d79056e4b5a0bf24c60f86023199bc762b3845860c6ca16dffd'),
    'common/AccountCommands.pyc': (5534, 'ba439d8badead15bba4f28708c1822630c1d58fe4699bd07d76d99db345dc2fe'),
    'client/gui/shared/gui_items/processors/vehicle.pyc': (21686, 'c2e6e1896bd3f71ab41ae89de70528a74268c7e67fe677d8bb498dc8b9c7bff2'),
    'client/gui/Scaleform/daapi/view/lobby/hangar/TechnicalMaintenance.pyc': (16962, '11933820a86f74bebc5caae8f11a47d887bab911e517f51c2e1d17c094a2259d'),
    'client/gui/Scaleform/daapi/view/meta/TechnicalMaintenanceMeta.pyc': (3293, '7761c496e571c57f3a982a6c7808460a68d1ec5374e3b3e8d721ef09b2967e4f'),
    'entity_defs/account.def': (None, '883ec72e77675600f245e0f0aea8837e35c2c4bb9e7a5c5d70f3656d9d076674'),
}
OPCODE_SHA = 'acfe212847ecb81ca28bdab976a3caacff3568b45a9e8ca78d6957f9f3ef4884'
SELECT = ('setAndFillLayouts', '__setAndFillLayouts_onShopSynced', 'synchronize',
          'fillVehicle', '__setVehicleLayouts', 'setRefillSettings', 'repair',
          'populateTechnicalMaintenance', '_populate', 'as_setDataS',
          'VehicleLayoutProcessor._request', 'VehicleLayoutProcessor._successHandler',
          'VehicleLayoutProcessor._errorHandler', 'PlayerAccount.update',
          'PlayerAccount._update', 'onCmdResponseExt', '_doCmdIntArr',
          '__sendSyncRequest', '__onSyncResponse')


def audit_sources(original_root: Path | str, opcode_file: Path | str) -> dict:
    root = no_links(original_root)
    catalog = audit_catalog(root)
    op = read(no_links(opcode_file), 32768, OPCODE_SHA)
    table = opcode_table(op.decode('utf-8'))
    sources, selected, definitions = {}, {}, None
    for rel, (size, digest) in PINS.items():
        data = read(root / PREFIX / rel, 256 * 1024, digest)
        if size is not None and len(data) != size:
            raise ValueError('native maintenance source size mismatch: ' + rel)
        sources[PREFIX + rel] = {'bytes': len(data), 'sha256': digest}
        if rel.endswith('.pyc'):
            rows = inspect(data, table)
            code = dict(records(parse_pyc(data)))
            picked = [r for r in rows if any(r['qualified_name'].endswith('.' + name) for name in SELECT)]
            for row in picked:
                row['code_sha256'] = hashlib.sha256(code[row['qualified_name']]['code']).hexdigest()
            if rel == 'common/AccountCommands.pyc':
                instructions = rows[0]['instructions']
                constants = {row['value']: instructions[index - 1].get('value')
                             for index, row in enumerate(instructions)
                             if index and row['opname'] == 'STORE_NAME'
                             and row.get('value') in ('CMD_SET_AND_FILL_LAYOUTS', 'RES_SUCCESS',
                                                     'RES_NOT_AVAILABLE', 'RES_WRONG_ARGS', 'RES_SHOP_DESYNC')}
                if constants != {'CMD_SET_AND_FILL_LAYOUTS': 108, 'RES_SUCCESS': 0,
                                 'RES_NOT_AVAILABLE': -10, 'RES_WRONG_ARGS': -2, 'RES_SHOP_DESYNC': -4}:
                    raise ValueError('native command constants mismatch')
                selected['command_constants'] = constants
            selected[rel] = picked
        else:
            node = decode(data, max_bytes=256 * 1024)
            definitions = {}
            for group in node.get('children', []):
                for method in group['data'].get('children', []) if isinstance(group['data'], dict) else []:
                    if method['name'] in ('update', 'doCmdIntArr', 'onCmdResponseExt'):
                        definitions[method['name']] = {'group': group['name'], 'definition': method['data']}
            if set(definitions) != {'update', 'doCmdIntArr', 'onCmdResponseExt'}:
                raise ValueError('native service method definitions missing')
    return {'schema': 'p09d-native-ammo-static.v1', 'status': 'PASS_STATIC_NATIVE_AMMO_SOURCE',
            'classification': 'VERIFIED_STATIC', 'original_root': str(root),
            'sources': sources, 'opcode_sha256': OPCODE_SHA, 'catalog': catalog,
            'records': selected, 'definitions': definitions,
            'request': {'command': 108, 'method': 'doCmdIntArr', 'message_id': 151,
                        'shape': '[shopRev, vehicleInventoryId, shellIntCount, signedShellId/count pairs, equipmentIntCount, equipmentId/count pairs]',
                        'shop_revision_is_not_account_revision': True},
            'response': {'method': 'onCmdResponseExt', 'message_id': 77,
                         'success_result': 0, 'no_purchase_context': {},
                         'does_not_update_inventory': True},
            'update': {'method': 'Account.update', 'message_id_candidate': 87,
                       'route_classification': 'INFERRED_REQUIRES_NATIVE_TRACE',
                       'arguments': ['STRING: primitive protocol2 inventory delta'],
                       'required_delta_fields': ['prevRev', 'rev', 'inventory'],
                       'original_callback': '_update(True, diff)',
                       'native_verification': 'NOT_RUN'},
            'unsupported': ['purchase', 'repair', 'automatic_service', 'equipment_changes']}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--original-root', type=Path, required=True)
    p.add_argument('--opcode-file', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    args = p.parse_args(argv)
    out = no_links(args.out)
    allowed = no_links(ROOT / 'local/evidence')
    if not out.is_relative_to(allowed) or out == allowed or out.exists():
        p.error('fresh own local/evidence output required')
    result = audit_sources(args.original_root, args.opcode_file)
    out.mkdir(parents=True)
    (out / 'receipt.json').write_text(json.dumps(result, ensure_ascii=True, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'status': result['status'], 'receipt': str(out / 'receipt.json')}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
