# -*- coding: utf-8 -*-
"""Owned code tests. Fake engine modules prove delegation, never native login."""
import os
import sys
import types
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'client_patch'))
import project_network as network
import project_auth as auth


class EndpointTests(unittest.TestCase):
    def test_all_private_ranges_and_boundary_ports_are_canonical(self):
        for endpoint in ('10.0.0.0:1024', '10.255.255.255:65535',
                         '172.16.0.0:1024', '172.31.255.255:65535',
                         '192.168.0.0:1024', '192.168.255.255:65535',
                         '192.168.50.10:20130'):
            self.assertEqual(network.validate_endpoint(endpoint, network.POLICY), endpoint)

    def test_public_dns_ipv6_wildcard_and_noncanonical_spellings_refuse(self):
        for host in ('127.0.0.1', '0.0.0.0', '169.254.1.1', '100.64.1.1',
                     '172.15.255.255', '172.32.0.0', '192.169.1.1',
                     '224.0.0.1', '255.255.255.255', '8.8.8.8', 'localhost',
                     'server.local', '192.168.050.10', '192.168.50.010',
                     '192.168.50.-1', '192.168.50.+1', '192.168.50.256',
                     ' 192.168.50.10', '192.168.50.10 ', '192.168.50.10\n',
                     '192.168.50.10.', '::1', '::ffff:192.168.50.10',
                     '[::ffff:192.168.50.10]', u'１９２.168.50.10'):
            with self.assertRaises(ValueError):
                network.validate_endpoint(host+':20130', network.POLICY)
        for port in ('0', '1023', '65536', '20130 ', '020130', '+20130', '-1',
                     '20130/path', '20130?x', '20130#x', '20130:20131', u'２０１３０'):
            with self.assertRaises(ValueError):
                network.validate_endpoint('192.168.50.10:'+port, network.POLICY)

    def test_default_loopback_contract_and_historical_port_spelling(self):
        for value in ('127.0.0.1:1024', '127.0.0.1:65535', '127.0.0.1:02014'):
            self.assertEqual(network.validate_endpoint(value), value)
        for value in ('127.0.0.2:20130', '192.168.50.10:20130', 'localhost:20130',
                      '127.0.0.1:1023', '127.0.0.1:65536', '127.0.0.1:20014\n'):
            with self.assertRaises(ValueError):
                network.validate_endpoint(value)
        self.assertEqual(network.prepare_options('127.0.0.1:20014'),
                         {'endpoint':'127.0.0.1:20014',
                          'registration_url':'http://127.0.0.1:3092/register'})
        value = network.prepare_options('127.0.0.1:02014', registration_url='http://127.0.0.1:03091/register')
        self.assertEqual(value['registration_url'], 'http://127.0.0.1:03091/register')
        self.assertNotIn('network_policy', value)

    def test_unknown_policy_or_nontext_refuse(self):
        for policy in ('lan-test', 'LAN-TEST-V1', 'lan-test-v2', '', True, 1, []):
            with self.assertRaises(ValueError):
                network.validate_endpoint('192.168.50.10:20130', policy)
        for value in (None, True, 123, {}, []):
            with self.assertRaises(ValueError):
                network.validate_endpoint(value, network.POLICY)

    def test_lan_requires_explicit_modes_and_disables_all_registration(self):
        for p13, mixed in ((False, False), (True, False), (False, True), (1, True)):
            with self.assertRaises(ValueError):
                network.prepare_options('192.168.50.10:20130', network.POLICY,
                                        profile13=p13, mixed_ammo=mixed)
        for url in ('http://127.0.0.1:3092/register', 'http://192.168.50.10:3092/register',
                    'https://example.com/register'):
            with self.assertRaises(ValueError):
                network.prepare_options('192.168.50.10:20130', network.POLICY, url, True, True)
        result = network.prepare_options('192.168.50.10:20130', network.POLICY,
                                         profile13=True, mixed_ammo=True)
        self.assertEqual(result, {'endpoint':'192.168.50.10:20130',
                                 'registration_url':'', 'network_policy':'lan-test-v1'})

    def test_runtime_settings_cannot_silently_enable_lan_or_other_mode(self):
        good = {'endpoint':'192.168.50.10:20130', 'network_policy':'lan-test-v1',
                'enable_profile13_battle':True, 'enable_p06t_mixed_ammo':True}
        self.assertEqual(network.validate_settings(good), network.POLICY)
        for key in ('network_policy', 'enable_profile13_battle', 'enable_p06t_mixed_ammo'):
            value = dict(good)
            del value[key]
            with self.assertRaises(ValueError):
                network.validate_settings(value)
        self.assertIsNone(network.validate_settings({'endpoint':'127.0.0.1:20014'}))


class OriginalDelegationTests(unittest.TestCase):
    def setUp(self):
        self.saved = dict(sys.modules)
        names = ('external_strings_utils', 'ConnectionManager', 'gui', 'gui.Scaleform',
                 'gui.Scaleform.daapi', 'gui.Scaleform.daapi.view',
                 'gui.Scaleform.daapi.view.login',
                 'gui.Scaleform.daapi.view.login.LoginDispatcher')
        for name in names:
            module = types.ModuleType(name)
            module.__path__ = []
            sys.modules[name] = module
        self.calls, self.records = [], []
        calls = self.calls
        class FakeLoginView(object):
            def onLogin(view, user, password, host):
                calls.append((view, user, password, host))
                return 'original-result'
        self.view_class = FakeLoginView
        self.original_login = FakeLoginView.onLogin
        sys.modules['gui.Scaleform.daapi.view.login'].LoginView = FakeLoginView
        self.dispatcher = sys.modules['gui.Scaleform.daapi.view.login.LoginDispatcher']
        self.dispatcher.transport_marker = object()
        self.marker = self.dispatcher.transport_marker
        sys.modules['ConnectionManager'].LOG_DEBUG = lambda *args, **kwargs: None

    def tearDown(self):
        for name in list(sys.modules):
            if name not in self.saved:
                del sys.modules[name]
        sys.modules.update(self.saved)

    def record(self, name, **fields):
        self.records.append((name, fields))

    def test_lan_exact_target_delegates_to_original_and_preserves_secrets(self):
        endpoint = '192.168.50.10:20130'
        auth.install(endpoint, self.record, network.POLICY)
        view = self.view_class()
        password = u'  пароль LAN игрока  '
        self.assertEqual(view.onLogin(' Test@EXAMPLE.COM ', password, endpoint), 'original-result')
        self.assertEqual(self.calls[0][1], b'test@example.com')
        self.assertEqual(self.calls[0][2].strip(), password.encode('utf8'))
        self.assertEqual(self.calls[0][3], endpoint)
        self.assertIs(sys.modules['gui.Scaleform.daapi.view.login.LoginDispatcher'], self.dispatcher)
        self.assertIs(self.dispatcher.transport_marker, self.marker)
        self.assertNotIn(password, repr(self.records))
        self.assertNotIn('Test@EXAMPLE.COM', repr(self.records))
        for host in ('192.168.50.11:20130', '192.168.50.10:20131',
                     '127.0.0.1:20130', endpoint+' ', 'server.local:20130'):
            with self.assertRaises(ValueError):
                view.onLogin('test@example.com', password, host)
        self.assertEqual(len(self.calls), 1)

    def test_bad_config_refuses_before_imports_or_original_patch(self):
        with self.assertRaises(ValueError):
            auth.install('192.168.50.10:20130', self.record)
        self.assertEqual(self.view_class.onLogin, self.original_login)
        self.assertEqual(self.calls, [])
        self.assertEqual(self.records, [])

    def test_default_loopback_keeps_original_delegation(self):
        auth.install('127.0.0.1:20014', self.record)
        self.assertEqual(self.view_class().onLogin('test@example.com', 'x'*15,
                                                 '127.0.0.1:20014'), 'original-result')
        with self.assertRaises(ValueError):
            self.view_class().onLogin('test@example.com', 'x'*15, '192.168.50.10:20130')
        self.assertEqual(len(self.calls), 1)


if __name__ == '__main__':
    unittest.main()
