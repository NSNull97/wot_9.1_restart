"""Check existing own web accounts and immutable game snapshots over a restart.

Uses fresh real website sessions, never registration or internal/native/login.
Only the website login writes its ordinary session/rate/last_login fields.
SQLite snapshots use read-only connections; credentials and password hashes are
never written to evidence or stdout. Supports managed and external loopback sites.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import sys

from account_site_probe import Browser
from client_audit import ROOT, output_dir, read_limited, save_json


class ProbeFailure(Exception):
    pass


def check(value, code):
    if not value:
        raise ProbeFailure(code)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode('utf-8')


def local(path):
    path = Path(path).resolve(strict=True)
    check(path.is_relative_to((ROOT / 'local').resolve()), 'input_outside_local')
    return path


def json_file(path, maximum=32768):
    return json.loads(read_limited(local(path), maximum).decode('utf-8-sig'))


def readonly(path):
    connection = sqlite3.connect(local(path).as_uri() + '?mode=ro', uri=True, timeout=1)
    connection.row_factory = sqlite3.Row
    connection.execute('PRAGMA query_only=ON')
    return connection


def snapshot(web_path, game_path, users):
    identities, games = [], []
    with readonly(web_path) as web, readonly(game_path) as game:
        versions = {'identity': web.execute('PRAGMA user_version').fetchone()[0],
                    'game': game.execute('PRAGMA user_version').fetchone()[0]}
        check(versions['identity'] == 2, 'email_identity_migration_required')
        for user in users:
            column = 'email' if 'email' in user else 'username'
            value = user[column]
            row = web.execute('SELECT id,username,display_nickname,email,created_at,updated_at,last_login_at,password_hash '
                              'FROM users WHERE ' + column + '=?', (value,)).fetchone()
            check(row is not None, 'registered_identity_missing')
            identity = dict(row)
            check(type(identity['email']) is str, 'explicit_email_binding_required')
            user['_login_email'] = identity['email']
            if 'nickname' in user:
                check(identity['display_nickname'] == user['nickname'], 'stored_display_nickname_mismatch')
            identity['email_sha256'] = sha(identity.pop('email').encode('ascii'))
            identity['password_hash_sha256'] = sha(identity.pop('password_hash').encode('ascii'))
            identities.append(identity)
            row = game.execute('SELECT native_id,account_id,profile_json FROM game_profiles WHERE account_id=?',
                               (identity['id'],)).fetchone()
            if row is None:
                games.append({'account_id': identity['id'], 'profile': None})
                continue
            raw = row['profile_json'].encode('utf-8')
            check(len(raw) <= 8192, 'stored_profile_exceeds_limit')
            profile = json.loads(raw)
            check(profile['account_id'] == identity['id'] and profile['username'] == identity['display_nickname']
                  and profile['native_database_id'] == row['native_id'], 'stored_profile_identity_mismatch')
            check(profile['created_at_ms'] == identity['created_at'], 'stored_profile_registration_mismatch')
            games.append({'account_id': identity['id'], 'native_database_id': row['native_id'],
                          'profile_json_sha256': sha(raw), 'profile': profile})
        counts = {'identity_users': web.execute('SELECT COUNT(*) FROM users').fetchone()[0],
                  'game_profiles': game.execute('SELECT COUNT(*) FROM game_profiles').fetchone()[0]}
    # Connection context managers commit/rollback, but do not close SQLite handles.
    web.close(); game.close()
    immutable = [{k: v for k, v in item.items() if k != 'last_login_at'} for item in identities]
    return {'schema_versions': versions, 'counts': counts, 'identity_users': identities,
            'identity_immutable_sha256': sha(canonical(immutable)), 'game_profiles': games,
            'game_profiles_sha256': sha(canonical(games))}


def fixture_evidence(root, profile, catalog_version=2):
    directory = local(Path(root) / profile['account_id'] / ('r1-catalog2' if catalog_version == 2 else 'r1'))
    manifest = json_file(directory / 'manifest.json')
    compat = json_file(directory / 'compatibility.json')
    model = json_file(directory / 'fixture.json')
    if catalog_version == 2:
        check(manifest.get('compatibility_catalog_revision') == 2
              and compat.get('compatibility_catalog_revision') == 2, 'catalogue_revision_mismatch')
    for data in (manifest, compat):
        check(data['account_id'] == profile['account_id']
              and data['native_database_id'] == profile['native_database_id'], 'fixture_identity_mismatch')
    check(compat['client_name'] == profile['username'], 'fixture_username_mismatch')
    check(model['account_id'] == profile['account_id'] and model['display_name'] == profile['username']
          and model['resources'] == profile['resources'] and model['statistics'] == profile['statistics'],
          'fixture_domain_values_mismatch')
    source = manifest['profile_source']
    check(source.get('file') == 'profile-input.json' and source.get('relative_to') == 'fixture_directory',
          'fixture_profile_source_schema')
    raw = read_limited(local(directory / source['file']), 8192)
    check(sha(raw) == source['sha256'] and json.loads(raw) == profile, 'fixture_profile_source_mismatch')
    files = []
    for name in ('state.bin', 'shop.bin', 'dossier.bin'):
        path = local(directory / name)
        check(path.is_relative_to(directory), 'fixture_member_escape')
        payload = read_limited(path, 16384)
        entries = [row for row in manifest['files'] if row.get('file') == name]
        check(len(entries) == 1 and entries[0]['sha256'] == sha(payload)
              and entries[0]['bytes'] == len(payload), 'fixture_payload_hash_mismatch')
        files.append({'file': name, 'bytes': len(payload), 'sha256': sha(payload)})
    return {'directory': str(directory), 'manifest_sha256': sha(read_limited(directory / 'manifest.json', 32768)),
            'compatibility_sha256': sha(read_limited(directory / 'compatibility.json', 32768)),
            'profile_input_sha256': source['sha256'], 'files': files}


def api(browser, path):
    status, text = browser.request(path)
    check(status == 200 and len(text.encode('utf-8')) <= 32768, 'website_api_unavailable_or_oversized')
    return json.loads(text)


def perform(args, report):
    settings = json_file(args.service_config)
    bridge = json_file(local(settings['runtime_dir']) / 'bridge.json')
    origin = 'http://127.0.0.1:' + str(settings['web_port'])
    users = json_file(args.credentials, 8192)
    check(type(users) is list and 2 <= len(users) <= 8, 'expected_two_to_eight_existing_users')
    for user in users:
        check(type(user) is dict and (
              (type(user.get('email')) is str and len(user['email']) <= 254
               and user['email'].isascii() and user['email'].count('@') == 1)
              or (type(user.get('username')) is str and re.fullmatch('[a-z0-9_]{3,24}', user['username'])))
              and type(user.get('password')) is str and len(user['password'].encode('utf-8')) <= 512
              and type(user.get('case')) is str and re.fullmatch('[a-z0-9_]{1,32}', user['case']), 'credential_input_schema')
    expected = {}
    for entry in args.expect:
        key, separator, value = entry.partition('=')
        check(separator and key not in expected and value in ('ready', 'unlinked'), 'expected_state_argument')
        expected[key] = value
    check(set(expected) == {user['case'] for user in users}
          and len({user.get('email', user.get('username')) for user in users}) == len(users), 'expected_cases_mismatch')
    report.update({'origin': origin, 'expected': expected, 'native_login': 'NOT_RUN_BY_THIS_TOOL',
                   'side_effects': 'Normal web login sessions/rate counters/users.last_login_at only',
                   'sqlite_before_http': snapshot(bridge['web_database'], bridge['game_database'], users)})
    before = report['sqlite_before_http']
    results = []
    for index, user in enumerate(users):
        browser = Browser(origin)
        status, _ = browser.request('/login')
        check(status == 200 and browser.csrf, 'fresh_web_login_form_unavailable')
        status, _ = browser.request('/login', {'email': user['_login_email'], 'password': user['password']})
        check(status == 303, 'fresh_web_login_rejected_or_rate_limited')
        identity = before['identity_users'][index]
        web_profile = api(browser, '/api/profile')['profile']
        check(web_profile['id'] == identity['id'] and web_profile['username'] == identity['username']
              and web_profile['nickname'] == identity['display_nickname']
              and sha(web_profile['email'].encode('ascii')) == identity['email_sha256'], 'web_identity_mismatch')
        game = api(browser, '/api/game')
        foreign_id = before['identity_users'][(index + 1) % len(users)]['id']
        foreign = api(browser, '/api/game?account_id=' + foreign_id + '&id=' + foreign_id)
        check(foreign == game, 'foreign_query_changed_authenticated_game_data')
        check(game.get('state') == expected[user['case']], 'unexpected_game_state')
        stored = before['game_profiles'][index]['profile']
        evidence = None
        if expected[user['case']] == 'ready':
            check(stored is not None, 'ready_without_persisted_game_profile')
            check(game['account']['accountId'] == identity['id'] and game['account']['nickname'] == identity['display_nickname'], 'game_subject_mismatch')
            check(game['resources'] == {'credits': stored['resources']['credits'], 'gold': stored['resources']['gold'],
                                       'freeXP': stored['resources']['free_xp']}
                  and game['statistics'] == stored['statistics']
                  and game['snapshotRevision'] == stored['snapshot_revision'] and game['ruleset'] == 'test_lab',
                  'web_game_snapshot_values_mismatch')
            check(len(game['inventory']) == 1
                  and game['inventory'][0]['inventoryItemId'] == identity['id'] + ':starter-vehicle-v1', 'web_inventory_subject_mismatch')
            evidence = fixture_evidence(bridge['fixture_root'], stored, args.catalog_version)
        else:
            check(stored is None and game.get('account') is None and game.get('inventory') is None
                  and game.get('statistics') is None, 'unlinked_returned_fabricated_data')
        results.append({'case': user['case'], 'account_id': identity['id'], 'username': identity['username'],
                        'nickname': identity['display_nickname'],
                        'fresh_web_login': 'PASS', 'foreign_query_ignored': 'PASS', 'game': game, 'fixture': evidence})
        report['accounts'] = results
    after = snapshot(bridge['web_database'], bridge['game_database'], users)
    report['sqlite_after_http'] = after
    check(after['identity_immutable_sha256'] == before['identity_immutable_sha256'], 'web_login_changed_immutable_identity')
    check(after['game_profiles_sha256'] == before['game_profiles_sha256'] and after['counts'] == before['counts'],
          'game_profiles_changed_during_read_probe')
    report['http_readonly_game_profiles'] = 'PASS'
    if args.compare:
        previous = json_file(args.compare, 256 * 1024)
        check(previous.get('status') == 'PASS', 'comparison_baseline_not_pass')
        baseline = previous['sqlite_after_http']
        check(before['schema_versions'] == baseline['schema_versions'] and before['counts'] == baseline['counts']
              and before['identity_immutable_sha256'] == baseline['identity_immutable_sha256']
              and before['game_profiles_sha256'] == baseline['game_profiles_sha256'], 'restart_changed_persistent_account_state')
        old = {item['account_id']: item for item in previous['accounts']}
        check(set(old) == {item['account_id'] for item in results}, 'restart_account_set_changed')
        for result in results:
            check(result['game'] == old[result['account_id']]['game']
                  and result['fixture'] == old[result['account_id']]['fixture'], 'restart_changed_web_values_or_fixture_hashes')
        report['restart_comparison'] = {'status': 'PASS', 'baseline': str(local(args.compare))}
    else:
        report['restart_comparison'] = {'status': 'NOT_RUN', 'reason': 'No --compare baseline supplied'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--service-config', required=True)
    parser.add_argument('--credentials', required=True)
    parser.add_argument('--expect', action='append', required=True, help='Exact existing credential case=ready|unlinked')
    parser.add_argument('--compare', help='Earlier PASS account-state.json; requires unchanged game profiles across restart')
    parser.add_argument('--catalog-version', type=int, choices=(1, 2), default=2,
                        help='Native representation to inspect; domain profile revision stays1')
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    out = output_dir(args.out)
    check(not any(out.iterdir()), 'fresh_evidence_directory_required')
    report = {'status': 'FAIL', 'scope': 'Real existing-account HTTP and readonly SQLite/fixture comparison'}
    try:
        perform(args, report)
        report['status'] = 'PASS'
    except ProbeFailure as error:
        report['failure'] = str(error)
    except Exception as error:
        # Never include incoming bodies, credentials, cookies or raw SQL errors.
        report['failure'] = 'unexpected_' + type(error).__name__
    save_json(out / 'account-state.json', report)
    print(json.dumps({'status': report['status'], 'evidence': str(out / 'account-state.json'),
                      'native_login': 'NOT_RUN_BY_THIS_TOOL'}))
    return 0 if report['status'] == 'PASS' else 1


if __name__ == '__main__':
    sys.exit(main())
