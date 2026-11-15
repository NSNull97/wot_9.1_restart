"""Bind source-pinned Prohorovka foliage to a stopped local 5a stand."""

import argparse
import os
from pathlib import Path
import sys

from tools.content0_s5a_stand import ROOT, check_ports, digest, json_unique, no_link, read_stable, write_json
from tools.content0_s5a_stand_lock import StandLock


ASSET = '05_prohorovka'
SCHEMA = 'content0-s5a-prohorovka-bush-volumes.v1'
LIMIT = 2 * 1024 * 1024


def checked_artifact(stand, profiles, raw):
    from tools.prohorovka_foliage import APPROVED_PROHOROVKA_FOLIAGE_PINS

    sha256 = digest(raw)
    if profiles.get('map') != ASSET or sha256 not in APPROVED_PROHOROVKA_FOLIAGE_PINS:
        raise ValueError('Prohorovka foliage map or canonical artifact digest mismatch')
    document = json_unique(raw)
    catalog_pin = document['fallen_tree_catalog_sha256']
    catalog_ref = profiles['catalog']
    if document['schema'] != SCHEMA or document['map'] != ASSET or catalog_ref['sha256'] != catalog_pin:
        raise ValueError('Prohorovka foliage does not match the battle contact catalog')
    catalog_path = Path(catalog_ref['path'])
    if not catalog_path.is_absolute():
        raise ValueError('Prohorovka contact catalog path must be absolute')
    no_link(catalog_path, stand)
    if digest(read_stable(catalog_path)) != catalog_pin:
        raise ValueError('Prohorovka contact catalog bytes differ from the foliage pin')
    return {'schema': SCHEMA, 'sha256': sha256, 'catalog_sha256': catalog_pin}


def verify_prohorovka_binding(stand, profiles, foliage, receipt):
    if (type(foliage) is not dict or set(foliage) != {'version', 'file', 'sha256'}
            or type(foliage['version']) is not int or foliage['version'] != 1):
        raise ValueError('Prohorovka foliage gateway binding is invalid')
    target = Path(foliage['file'])
    if not target.is_absolute():
        raise ValueError('Prohorovka foliage path must be absolute')
    no_link(target, stand)
    expected = checked_artifact(stand, profiles, read_stable(target, LIMIT))
    if receipt != {**expected, 'file': str(target)} or foliage['sha256'] != expected['sha256']:
        raise ValueError('Prohorovka foliage launch receipt mismatch')


def bind(stand, artifact):
    from tools.content0_s5a_scene_apply import active_foliage_receipt, no_own_processes

    local = (ROOT / 'local').resolve(strict=True)
    no_link(stand, local / 'stands')
    no_link(artifact, local / 'evidence')
    stand = stand.resolve(strict=True)
    if stand == local / 'stands':
        raise ValueError('select a single owned stand')

    with StandLock(stand):
        snapshot = json_unique(read_stable(stand / 'snapshot-receipt.json'))
        check_ports(snapshot['ports'])
        no_own_processes(stand)
        config_path = stand / 'config-receipt.json'
        gateway_path = stand / 'gateway.json'
        profile_path = stand / 'battle-profiles.json'
        marker = stand / 'scene-update-in-progress.json'
        refresh = stand / 'resource-refresh-in-progress.json'
        target = stand / 'runtime/prohorovka-foliage.v1.json'
        gateway_next = stand / 'gateway.prohorovka-next.json'
        config_next = stand / 'config-receipt.prohorovka-next.json'
        for path in (config_path, gateway_path, profile_path, marker, refresh, target, gateway_next, config_next):
            no_link(path, stand)
        if any(path.exists() for path in (marker, refresh, target, gateway_next, config_next)):
            raise ValueError('stand already bound or has an unfinished update')
        config_raw = read_stable(config_path)
        gateway_raw = read_stable(gateway_path)
        profile_raw = read_stable(profile_path)
        config = json_unique(config_raw)
        gateway = json_unique(gateway_raw)
        if (config['status'] != 'CONFIGURED_NOT_LAUNCHED'
                or config['config_sha256']['gateway'] != digest(gateway_raw)
                or config['battle_profiles_sha256'] != digest(profile_raw)
                or gateway.get('camouflage_v1') is not True
                or 'foliage_v1' in gateway or 'prohorovka_foliage' in config
                or active_foliage_receipt(config) is not None):
            raise ValueError('stand setup changed or already has a foliage binding')

        raw = read_stable(artifact, LIMIT)
        receipt = checked_artifact(stand, json_unique(profile_raw), raw)
        backup = stand / 'before-prohorovka-foliage'
        no_link(backup, stand)
        backup.mkdir()
        (backup / 'gateway.json').write_bytes(gateway_raw)
        (backup / 'config-receipt.json').write_bytes(config_raw)
        write_json(marker, {'backup': str(backup), 'artifact': str(target)})
        with target.open('xb') as output:
            output.write(raw)
        gateway['foliage_v1'] = {'version': 1, 'file': str(target), 'sha256': receipt['sha256']}
        config['prohorovka_foliage'] = {**receipt, 'file': str(target)}
        write_json(gateway_next, gateway)
        config['config_sha256']['gateway'] = digest(read_stable(gateway_next))
        write_json(config_next, config)
        os.replace(gateway_next, gateway_path)
        os.replace(config_next, config_path)
        verify_prohorovka_binding(stand, json_unique(profile_raw), gateway['foliage_v1'], config['prohorovka_foliage'])
        marker.unlink()
        return config['prohorovka_foliage']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stand', required=True, type=Path)
    parser.add_argument('--artifact', required=True, type=Path)
    args = parser.parse_args()
    try:
        receipt = bind(args.stand, args.artifact)
    except (OSError, ValueError, KeyError, TypeError) as error:
        print('Prohorovka foliage binding refused: ' + str(error), file=sys.stderr)
        return 1
    print('Prohorovka foliage bound: ' + receipt['sha256'])
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
