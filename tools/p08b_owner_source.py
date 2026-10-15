"""Explicit P08B owner grants from immutable #717 descriptor definitions.

The historical A exports remain A evidence. Their account-independent compact
descriptors are definitions for a new authoritative test_lab grant to a real
project owner. No native B export/delivery or historical WG grant is claimed.
Frozen profile4 chain, generators and evidence validators remain unchanged.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from contextlib import closing
import hashlib
import json
from pathlib import Path
import re
import sqlite3

from game_profile_tx import TransactionError
from p08b_battle_projection import BattleProjectionSource
from p08b_battle_store import BattleStore
from p09d_ammo_projection import canonical
from p09e_research_catalog import load_catalog
from p09e_research_store import ResearchStore, POLICY as RESEARCH_POLICY
from destructible_catalog import no_links
import test_garage_state as garage
import ms1_crew_state as crew
import ms1_ammo_state as ammo

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / 'local/evidence/20261015-p08b-01'
POLICY = 'test_lab.p08b-owned-source.v1'
PROFILE1_FIELDS = ('profile_version', 'account_id', 'username', 'native_database_id',
                   'created_at_ms', 'snapshot_revision', 'resources', 'statistics')
DEFINITIONS = {
    'inputs/native-ms1-crew': 'df0a9c26181a4efd65bfc8e9c34e2fbabc6f92a860db5676355890e400377a65',
    'inputs/native-ms1-ammo': '683daac81143a9d7edfbe671870ba163db088c54f5101fa52e077f596ebbfc74',
}
PROFILE_TABLE_SQL = ('CREATE TABLE game_profiles(native_id INTEGER PRIMARY KEY AUTOINCREMENT,'
    'account_id TEXT NOT NULL UNIQUE,profile_json TEXT NOT NULL)')


def require(value, code='INVALID_OWNER_SOURCE'):
    if not value:
        raise TransactionError(code)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _canonical_profile_schema(db):
    """Use the accepted P09E harness base DDL only in a new staging copy."""
    sql = db.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='game_profiles'").fetchone()[0]
    normalize = lambda text: re.sub(r'\s+', '', text).lower()
    canonical_sql = normalize(PROFILE_TABLE_SQL)
    legacy_sql = canonical_sql.replace('autoincrement,', 'autoincrementcheck(native_idbetween1and2147483647),')
    require(normalize(sql) in (canonical_sql, legacy_sql), 'LEGACY_PROFILE_SCHEMA_UNSUPPORTED')
    if normalize(sql) == canonical_sql:
        return
    rows = db.execute('SELECT native_id,account_id,profile_json FROM game_profiles ORDER BY native_id').fetchall()
    require(len(rows) <= 64 and all(type(row[0]) is int and 1 <= row[0] < 2**31 for row in rows), 'OWNER_ID_BOUND')
    sequence = db.execute("SELECT seq FROM sqlite_sequence WHERE name='game_profiles'").fetchone()
    db.execute('BEGIN IMMEDIATE')
    try:
        db.execute('ALTER TABLE game_profiles RENAME TO legacy_game_profiles')
        db.execute(PROFILE_TABLE_SQL)
        db.executemany('INSERT INTO game_profiles VALUES (?,?,?)', rows)
        db.execute('DROP TABLE legacy_game_profiles')
        if sequence is not None:
            require(db.execute("UPDATE sqlite_sequence SET seq=? WHERE name='game_profiles'", sequence).rowcount == 1)
        require(db.execute('SELECT native_id,account_id,profile_json FROM game_profiles ORDER BY native_id').fetchall() == rows,
                'OTHER_OWNER_CHANGED')
        db.commit()
    except Exception:
        db.rollback()
        raise


def _base_profile(profile4):
    require(type(profile4) is dict and len(canonical(profile4)) <= 8192)
    require(all(key in profile4 for key in PROFILE1_FIELDS))
    value = {key: deepcopy(profile4[key]) for key in PROFILE1_FIELDS}
    value.update(profile_version=1, snapshot_revision=1)
    return garage.validate_base_profile(value)


class OwnerProjectionSource(BattleProjectionSource):
    """Typed, deterministic owner source, separate from frozen profile4 proof."""

    def __init__(self, anchor_bundle, catalog, base_profile1, *, granted_at_ms):
        require(type(base_profile1) is dict and len(canonical(base_profile1)) <= 8192)
        base = garage.validate_base_profile(deepcopy(base_profile1))
        # This verifies the unchanged historical source, not the new owner.
        anchor = BattleProjectionSource(anchor_bundle, catalog)
        require(base['account_id'] != anchor.profile['account_id'], 'ANCHOR_OWNER_HAS_EXISTING_SOURCE')
        self.bundle, self.catalog = anchor.bundle, catalog
        definitions = {}
        for content_id, digest in DEFINITIONS.items():
            raw = self.bundle.read(content_id)
            require(sha(raw) == digest, 'DEFINITION_CHECKPOINT_CHANGED')
            envelope = self.bundle.read_json(content_id)
            require(envelope.get('version') == 1 and type(envelope.get('data')) is dict)
            definitions[content_id] = envelope
        native_crew = definitions['inputs/native-ms1-crew']['data']
        native_ammo = definitions['inputs/native-ms1-ammo']['data']
        require(native_crew['selection_before']['database_id'] == 1
            and native_ammo['selection_before']['database_id'] == 1, 'DEFINITION_OWNER_CHANGED')
        require(type(granted_at_ms) is int and base['created_at_ms'] <= granted_at_ms <= 2147483647997)
        # Pure original builders create owner IDs from this owner's identity.
        # They never edit A's profile, native marker or descriptor objects.
        ms1, is7, _ = garage.read_native_inputs(self.bundle.path('inputs/native-ms1'),
                                               self.bundle.path('inputs/native-is7'))
        self.profiles = {1: base}
        self.profiles[2] = garage.promote_profile(base, sha(canonical(base)), granted_at_ms)
        model, compat, trees, preservation = garage.build_payloads(self.profiles[2], base,
            sha(canonical(base)), ms1, is7)
        intermediate = self._intermediate(2, model, compat, trees, preservation)
        self.profiles[3] = crew.promote_profile(self.profiles[2], sha(canonical(self.profiles[2])),
            DEFINITIONS['inputs/native-ms1-crew'], granted_at_ms + 1)
        model, compat, trees, preservation = crew.build(intermediate, self.profiles[3], native_crew)
        intermediate = self._intermediate(3, model, compat, trees, preservation)
        self.profiles[4] = ammo.promote_profile(self.profiles[3], sha(canonical(self.profiles[3])),
            DEFINITIONS['inputs/native-ms1-ammo'], granted_at_ms + 2)
        model, compat, trees, preservation = ammo.build(intermediate, self.profiles[4], native_ammo)
        self.profile = deepcopy(self.profiles[4])
        self.profile_bytes = canonical(self.profile)
        self.fixture, self.compatibility = model, compat
        self.trees = trees
        self.raw = {name: ammo.encode_data(value) for name, value in trees.items()}
        self.descriptors = {row['role']: row['compact_descr_hex'] for row in native_crew['crew']}
        require(self.trees['shop.bin']['rev'] == 3 and self.trees['state.bin']['rev'] == 1)
        require(self.trees['state.bin']['inventory'][1]['crew'] == {1: [1, 2], 2: [None] * 5})
        self.proof = {
            'schema': 'P08B-owned-source.v1', 'policy': POLICY,
            'owner': {key: base[key] for key in ('account_id', 'native_database_id', 'username', 'created_at_ms')},
            'canonical_base_sha256': sha(canonical(base)),
            'anchor_bundle_sha256': anchor.bundle_sha256,
            'definition_exports': [{'content_id': key, 'sha256': digest,
                'observed_native_database_id': 1, 'observed_account_id': anchor.profile['account_id'],
                'use': 'account-independent definitions only'}
                for key, digest in sorted(DEFINITIONS.items())],
            'profiles': {str(version): sha(canonical(value)) for version, value in self.profiles.items()},
            'payloads': {name: sha(raw) for name, raw in self.raw.items()},
            'native_owner_export': 'NOT_RUN', 'native_delivery': 'NOT_RUN',
        }
        self.bundle_sha256 = sha(canonical(self.proof))

    def _intermediate(self, version, model, compat, trees, preservation):
        # A logical artifact ID for the pure historical builders; this is not
        # an invented native run or a path asserted to contain an old fixture.
        return {'directory': Path('P08B-owned-source.v1') / ('profile' + str(version)),
            'manifest_raw': canonical({'schema': POLICY, 'profile_version': version,
                                       'profile_sha256': sha(canonical(self.profiles[version]))}),
            'manifest': {'preservation': preservation}, 'model': model,
            'compatibility': compat, 'trees': trees,
            'payloads': {name: ammo.encode_data(value) for name, value in trees.items()}}

    @classmethod
    def from_profile4(cls, anchor_bundle, catalog, profile4):
        require(type(profile4) is dict and profile4.get('profile_version') == 4)
        require(type(profile4.get('test_grant')) is dict)
        source = cls(anchor_bundle, catalog, _base_profile(profile4),
                     granted_at_ms=profile4['test_grant'].get('granted_at_ms'))
        require(canonical(source.profile) == canonical(profile4), 'OWNER_GRANT_CHAIN_CHANGED')
        return source

    def export(self, directory):
        directory = no_links(directory).resolve()
        require(directory.is_relative_to(EVIDENCE.resolve()) and not directory.exists(), 'FRESH_OWNER_SOURCE_REQUIRED')
        directory.mkdir(parents=True)
        for version, value in self.profiles.items():
            (directory / ('profile' + str(version) + '.json')).write_bytes(canonical(value))
        for name, raw in self.raw.items():
            (directory / name).write_bytes(raw)
        (directory / 'owner-source.json').write_bytes(canonical(self.proof))
        return {'source_sha256': self.bundle_sha256, 'directory': str(directory)}


def projection_source(anchor_bundle, catalog, database, account_id):
    """Rebuild the trusted per-owner source, checking its persisted binding."""
    anchor = BattleProjectionSource(anchor_bundle, catalog)
    if anchor.profile['account_id'] == account_id:
        return anchor
    path = no_links(database).resolve(strict=True)
    with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)) as db:
        row = db.execute('SELECT base_json,base_sha256,bundle_sha256 FROM p09d_import WHERE account_id=?', (account_id,)).fetchone()
    require(row is not None and type(row[0]) is str and len(row[0]) <= 8192, 'OWNER_SOURCE_REQUIRED')
    require(sha(row[0].encode('ascii')) == row[1], 'CORRUPT_OWNER_SOURCE')
    profile4 = json.loads(row[0])
    require(profile4.get('account_id') == account_id, 'FOREIGN_ACCOUNT')
    source = OwnerProjectionSource.from_profile4(anchor_bundle, catalog, profile4)
    require(source.bundle_sha256 == row[2], 'OWNER_SOURCE_BINDING_CHANGED')
    return source


def stage(database, identity_database, account_id, anchor_bundle, original_root, out, granted_at_ms):
    """Build a new isolated DB; source databases are opened read-only."""
    out = no_links(out).resolve()
    require(out.is_relative_to(EVIDENCE.resolve()) and not out.exists(), 'FRESH_ISOLATED_OUTPUT_REQUIRED')
    original_db = no_links(database).resolve(strict=True)
    identity_db = no_links(identity_database).resolve(strict=True)
    with closing(sqlite3.connect(original_db.as_uri() + '?mode=ro', uri=True)) as db:
        require({r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            == {'game_meta', 'game_profiles', 'game_limits', 'sqlite_sequence'}, 'LEGACY_PROFILE_STORE_REQUIRED')
        row = db.execute('SELECT native_id,profile_json FROM game_profiles WHERE account_id=?', (account_id,)).fetchone()
        require(row is not None and len(row[1]) <= 8192, 'OWNER_PROFILE1_REQUIRED')
        profile1 = garage.validate_base_profile(json.loads(row[1]))
        require(profile1['account_id'] == account_id and profile1['native_database_id'] == row[0], 'FOREIGN_ACCOUNT')
        source_profile_sha = sha(row[1].encode('utf8'))
    with closing(sqlite3.connect(identity_db.as_uri() + '?mode=ro', uri=True)) as db:
        identity = db.execute('SELECT id,display_nickname,created_at FROM users WHERE id=?', (account_id,)).fetchone()
    require(identity == (account_id, profile1['username'], profile1['created_at_ms']), 'WEBSITE_OWNER_MISMATCH')
    catalog = load_catalog(original_root)
    source = OwnerProjectionSource(anchor_bundle, catalog, profile1, granted_at_ms=granted_at_ms)
    out.mkdir(parents=True)
    destination = out / 'game.sqlite'
    legacy_backup = out / 'legacy-before.sqlite'
    with closing(sqlite3.connect(original_db.as_uri() + '?mode=ro', uri=True)) as before, closing(sqlite3.connect(legacy_backup)) as after:
        before.backup(after)
    with closing(sqlite3.connect(legacy_backup.as_uri() + '?mode=ro', uri=True)) as before, closing(sqlite3.connect(destination)) as after:
        before.backup(after)
    with closing(sqlite3.connect(destination)) as db:
        _canonical_profile_schema(db)
    migrations = []
    with closing(sqlite3.connect(destination)) as db, db:
        unchanged = db.execute('SELECT native_id,account_id,profile_json FROM game_profiles WHERE account_id!=? ORDER BY native_id', (account_id,)).fetchall()
        require(db.execute('UPDATE game_profiles SET profile_json=? WHERE account_id=? AND native_id=? AND profile_json=?',
            (source.profile_bytes.decode('ascii'), account_id, row[0], row[1])).rowcount == 1, 'STALE_PROFILE')
    from p04d_crew_store import NativeCrewStore
    from p04f_crew_store import NativeCrewTransferStore
    from p04g_crew_store import NativeCrossVehicleCrewStore
    from p04h_crew_store import NativeRosterRecruitmentStore
    from p04i_crew_store import NativeCrewProgressionStore
    from p04j_crew_store import NativeCrewDismissalStore
    from p04k_crew_store import NativeBarracksRecruitmentStore
    with NativeCrewStore(destination) as store:
        migrations.append(store.migrate(source, account_id=account_id, original_root=original_root,
                                        grant={'grant_id': 'p09d-test-depot-v1', 'quantity_each': 100}))
        migrations.append(store.migrate_crew(source, account_id=account_id, original_root=original_root))
        migrations.append(store.recruit(dict(account_id=account_id, native_database_id=row[0],
            command_key='p08b-owner-source:recruit', expected_revision=6, wire_revision=1, layout=[3, 1, 1, 0]),
            authenticated_account_id=account_id))
    for cls, method in ((NativeCrewTransferStore, 'migrate_transfer'), (NativeCrossVehicleCrewStore, 'migrate_cross'),
            (NativeRosterRecruitmentStore, 'migrate_roster'), (NativeCrewProgressionStore, 'migrate_progression'),
            (NativeCrewDismissalStore, 'migrate_dismissal'), (NativeBarracksRecruitmentStore, 'migrate_barracks')):
        with cls(destination) as store:
            migrations.append(getattr(store, method)(source, account_id=account_id, original_root=original_root))
    with ResearchStore(destination, catalog) as store:
        migrations.append(store.migrate_research(source, account_id=account_id, policy=RESEARCH_POLICY))
    with BattleStore(destination, catalog) as store:
        migrations.append(store.activate(account_id=account_id, authenticated_account_id=account_id))
        result = store.publish(source, account_id, out / 'fixtures')
        require([tuple(value) for value in store.connection.execute(
            'SELECT native_id,account_id,profile_json FROM game_profiles WHERE account_id!=? ORDER BY native_id',
            (account_id,))] == unchanged, 'OTHER_OWNER_CHANGED')
    source.export(out / 'owner-source')
    require(projection_source(anchor_bundle, catalog, destination, account_id).bundle_sha256 == source.bundle_sha256)
    receipt = {'schema': 'p08b-owner-stage.v1', 'status': 'PASS_AUTOMATIC_OWNER_GRANT_MIGRATION',
        'database': str(destination), 'account_id': account_id, 'native_database_id': row[0],
        'source_profile1_sha256': source_profile_sha, 'source_sha256': source.bundle_sha256,
        'canonical_base_schema': 'accepted-p09e-harness', 'legacy_backup_sha256': sha(legacy_backup.read_bytes()),
        'policy': POLICY, 'migrations': migrations, 'fixture_dir': result['fixture_dir'],
        'other_profiles_unchanged': True, 'native_B_export': 'NOT_RUN', 'native_B_delivery': 'NOT_RUN'}
    (out / 'receipt.json').write_bytes(canonical(receipt))
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='operation', required=True)
    seed = sub.add_parser('stage')
    for name in ('database', 'identity-database', 'account-id', 'anchor-bundle', 'original-root', 'out'):
        seed.add_argument('--' + name, required=True)
    seed.add_argument('--granted-at-ms', type=int, required=True)
    args = parser.parse_args()
    print(canonical(stage(args.database, args.identity_database, args.account_id, args.anchor_bundle,
                          args.original_root, args.out, args.granted_at_ms)).decode('ascii'))


if __name__ == '__main__':
    main()
