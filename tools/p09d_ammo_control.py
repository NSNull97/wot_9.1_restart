"""Produce public seven-step native diagnostic expectations from read-only DB.

No credentials are accepted or written. This is not a client launcher.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'client_patch'))
from p09d_ammo_scenario import checked_expected
from p09c_ammo_catalog import MOUNTS


def expected_from_database(path, account_id):
    path = Path(path).resolve(strict=True)
    with sqlite3.connect(path.as_uri() + '?mode=ro', uri=True) as connection:
        connection.execute('BEGIN')
        snapshot = connection.execute('SELECT revision,snapshot_json,snapshot_sha256 FROM game_snapshot WHERE account_id=?', (account_id,)).fetchone()
        profile = connection.execute('SELECT native_id,profile_json FROM game_profiles WHERE account_id=?', (account_id,)).fetchone()
        if snapshot is None or profile is None or snapshot[0] != 7 or len(snapshot[1]) > 16384 or len(profile[1]) > 8192:
            raise ValueError('exact reviewed existing revision7 account required')
        if hashlib.sha256(snapshot[1].encode('ascii')).hexdigest() != snapshot[2]:
            raise ValueError('authoritative snapshot checksum differs')
        aggregate, base = json.loads(snapshot[1]), json.loads(profile[1])
        if aggregate['revision'] != 7 or base['snapshot_revision'] != 7 or base['profile_version'] != 5 or base['account_id'] != account_id:
            raise ValueError('authoritative profile revision/account differs')
        rows = []
        for vehicle, mount_id in ((1, 'ms1-stock'), (2, 'is7-stock')):
            ammo = [v for v in aggregate['ammunition'] if v['mount_id'] == mount_id]
            if len(ammo) != 1:
                raise ValueError('authoritative mounted ammunition missing')
            keys = MOUNTS[mount_id].shell_ids
            rows.append({'vehicle_id': vehicle, 'loaded': [ammo[0]['loaded'][k] for k in keys],
                         'depot': [aggregate['depot'][k] for k in keys]})
        return checked_expected({'version': 1, 'database_id': profile[0], 'source_revision': 7, 'initial': rows})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', required=True, type=Path)
    parser.add_argument('--account-id', required=True)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    out = args.out.resolve()
    if not out.is_relative_to((ROOT / 'local/evidence').resolve()) or out.exists():
        parser.error('fresh own local/evidence output required')
    value = expected_from_database(args.database, args.account_id)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2); stream.write('\n')
    print(json.dumps({'status': 'PUBLIC_EXPECTATION_READY', 'path': str(out), 'source_revision': 7, 'credentials': False}))


if __name__ == '__main__':
    main()
