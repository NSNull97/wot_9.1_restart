"""Register own test users through the real local website and retain private inputs.

This checks HTTP registration/login and per-user profile isolation. It does not
claim native client compatibility; the later client runs consume the private
one-shot control files without printing their credentials.
"""
import argparse
import http.cookiejar
import json
from pathlib import Path
import re
import secrets
import urllib.error
import urllib.parse
import urllib.request

from client_audit import ROOT, output_dir, save_json


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class Browser:
    def __init__(self, origin):
        target = urllib.parse.urlsplit(origin)
        if target.scheme != 'http' or target.hostname != '127.0.0.1' or target.path or target.query or target.fragment or target.username:
            raise ValueError('Probe requires a numeric own loopback origin')
        self.origin = origin
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}),
                                                 urllib.request.HTTPCookieProcessor(self.jar), NoRedirect())
        self.csrf = None

    def request(self, path, data=None):
        headers = {}
        body = None
        if data is not None:
            headers = {'Origin': self.origin, 'Content-Type': 'application/x-www-form-urlencoded'}
            body = urllib.parse.urlencode({'csrf': self.csrf or '', **data}).encode('utf8')
        request = urllib.request.Request(self.origin + path, data=body, headers=headers)
        try:
            response = self.opener.open(request, timeout=10)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            raw = response.read(1024 * 1024 + 1)
            if len(raw) > 1024 * 1024:
                raise ValueError('Unexpected response size')
            text = raw.decode('utf8')
            match = re.search(r'name="csrf" value="([A-Za-z0-9_-]{43})"', text)
            if match:
                self.csrf = match.group(1)
            return response.status, text


def check(condition, message):
    if not condition:
        raise AssertionError(message)


def run(args):
    out = output_dir(args.out)
    if any(out.iterdir()):
        raise ValueError('New evidence output directory required')
    suffix = secrets.token_hex(3)
    users = [
        {'email': 'sr.ascii.' + suffix + '@example.test', 'nickname': 'sr_ascii_' + suffix, 'display_name': 'Test ASCII',
         'password': 'StalnoyRubezh2026_' + secrets.token_hex(6), 'case': 'ascii'},
        {'email': 'sr.utf8.' + suffix + '@example.test', 'nickname': 'Танкист_Ёж_' + suffix, 'display_name': 'Тест Unicode',
         'password': '  Пушка_сталь_Żółw_' + secrets.token_hex(6) + '  ', 'case': 'unicode_spaces'},
    ]
    # Preserve only locally so the native-client probes can use these exact inputs.
    save_json(out / 'test-credentials.json', users)
    results = []
    for user in users:
        browser = Browser(args.origin)
        status, _ = browser.request('/register')
        check(status == 200 and browser.csrf, 'Registration form/session unavailable')
        status, _ = browser.request('/register', {
            key: user[key] for key in ('email', 'nickname', 'display_name', 'password')
        } | {'password_confirm': user['password']})
        check(status == 303, 'Real website registration failed')
        status, text = browser.request('/api/profile')
        check(status == 200, 'Registered website session missing')
        profile = json.loads(text)['profile']
        check(profile['nickname'] == user['nickname'] and profile['email'] == user['email'], 'Wrong website profile')
        account_id = profile['id']
        fresh = Browser(args.origin)
        status, _ = fresh.request('/login')
        check(status == 200, 'Login form unavailable')
        status, _ = fresh.request('/login', {'email': user['email'], 'password': user['password'] + 'wrong'})
        check(status == 401, 'Wrong website password accepted')
        status, _ = fresh.request('/login', {'email': user['nickname'], 'password': user['password']})
        check(status in (400, 401, 422), 'Nickname accepted as a login')
        status, _ = fresh.request('/login', {'email': user['email'], 'password': user['password']})
        check(status == 303, 'Exact registered credentials rejected by website')
        status, text = fresh.request('/api/profile')
        check(status == 200 and json.loads(text)['profile']['id'] == account_id, 'Website relogin changed account_id')
        status, text = fresh.request('/api/game?account_id=00000000-0000-0000-0000-000000000000')
        check(status == 200, 'Website game adapter unavailable')
        game = json.loads(text)
        # Before first native login no game profile is assumed or fabricated.
        check(game.get('state') in ('unlinked', 'ready'), 'Configured game bridge was not reached')
        if game['state'] == 'ready':
            check(game.get('account', {}).get('accountId') == account_id or game.get('accountId') == account_id,
                  'Request query changed authenticated game subject')
        results.append({'case': user['case'], 'account_id': account_id, 'email': user['email'], 'nickname': user['nickname'],
                        'registration': 'PASS', 'web_login': 'PASS', 'web_wrong_password': 'PASS',
                        'nickname_login_rejected': 'PASS',
                        'profile_relogin': 'PASS', 'game_state_before_native': game.get('state'),
                        'created_at': profile['createdAt'], 'native_login': 'NOT_RUN'})
    check(results[0]['account_id'] != results[1]['account_id'], 'Two registrations share an account_id')
    anon = Browser(args.origin)
    status, _ = anon.request('/api/profile')
    check(status == 401, 'Anonymous profile leaked')
    status, _ = anon.request('/api/game')
    check(status == 401, 'Anonymous game state leaked')
    save_json(out / 'registration.json', {'status': 'PASS', 'authentication': 'email_only', 'users': results,
                                          'anonymous_profile_game': 'PASS', 'native_login': 'NOT_RUN'})
    print(json.dumps({'status': 'PASS', 'users': len(results), 'evidence': str(out / 'registration.json'),
                      'native_login': 'NOT_RUN'}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--origin', default='http://127.0.0.1:3092')
    parser.add_argument('--out', required=True)
    run(parser.parse_args())
