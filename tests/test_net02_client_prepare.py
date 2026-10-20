"""Offline prepare seam tests against active source and original data only."""
from pathlib import Path
import importlib.util
import sys
from types import SimpleNamespace
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))
spec = importlib.util.spec_from_file_location('_net02_interactive_candidate',
                                            ROOT/'tools/interactive_client.py')
candidate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(candidate)


class PrepareTests(unittest.TestCase):
    def test_actual_flag_parser_exposes_only_known_policy(self):
        import subprocess
        script = ROOT/'tools/interactive_client.py'
        # Only --help: the parser exits before prepare/install or config reads.
        import os
        env = dict(os.environ)
        env['PYTHONPATH'] = str(ROOT/'tools')
        result = subprocess.run([sys.executable, '-B', str(script), 'prepare', '--help'],
                                env=env, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        self.assertIn(b'--network-policy {lan-test-v1}', result.stdout)
        self.assertIn(b'registration disabled', result.stdout)

    def test_prepare_uses_same_owned_runtime_validator(self):
        args = SimpleNamespace(endpoint='192.168.50.10:20130', network_policy='lan-test-v1',
                               registration_url=None)
        options = candidate.network_options(args, True, True)
        self.assertEqual(options, {'endpoint':args.endpoint, 'registration_url':'',
                                   'network_policy':'lan-test-v1'})
        args.registration_url = 'http://127.0.0.1:3092/register'
        with self.assertRaises(ValueError):
            candidate.network_options(args, True, True)
        args.registration_url = None
        for p13, mixed in ((False, True), (True, False)):
            with self.assertRaises(ValueError):
                candidate.network_options(args, p13, mixed)
        args.network_policy = None
        with self.assertRaises(ValueError):
            candidate.network_options(args, True, True)
        args.endpoint = '127.0.0.1:20014'
        self.assertEqual(candidate.network_options(args, False, False),
                         {'endpoint':args.endpoint,
                          'registration_url':'http://127.0.0.1:3092/register'})

    def test_actual_original_gui_keeps_all_urls_empty_in_lan(self):
        from client_audit import config
        _, paths = config()
        original = paths['original_client_root']
        payloads, evidence = candidate.interactive_resource_overrides(original)
        gui = ET.fromstring(payloads['res_mods/0.9.1/gui/gui_settings.xml'])
        source_urls = list(evidence['empty_url_settings'])
        options = {'endpoint':'192.168.50.10:20130', 'registration_url':'',
                   'network_policy':'lan-test-v1'}
        candidate.apply_registration(gui, evidence, options)
        self.assertEqual(evidence['empty_url_settings'], source_urls)
        self.assertIn('registrationURL', source_urls)
        self.assertFalse(evidence['registration_enabled'])
        self.assertEqual(evidence['registration_url'], '')
        url_nodes = [node for node in gui.iter() if node.findtext('type', '').lower() == 'url']
        self.assertGreater(len(url_nodes), 0)
        for node in url_nodes:
            field = node.find('value')
            if field is None:
                field = node
            self.assertIn(field.text, (None, ''))
        self.assertNotIn(b'127.0.0.1', ET.tostring(gui))

    def test_default_registration_retains_original_local_route_semantics(self):
        from client_audit import config
        _, paths = config()
        payloads, evidence = candidate.interactive_resource_overrides(paths['original_client_root'])
        gui = ET.fromstring(payloads['res_mods/0.9.1/gui/gui_settings.xml'])
        candidate.apply_registration(gui, evidence, {'endpoint':'127.0.0.1:20014',
                                                    'registration_url':'http://127.0.0.1:3091/register'})
        nodes = [node for node in gui.iter() if node.findtext('name') == 'registrationURL']
        field = nodes[0].find('value')
        if field is None:
            field = nodes[0]
        self.assertEqual(field.text, 'http://127.0.0.1:3091/register')
        self.assertNotIn('registrationURL', evidence['empty_url_settings'])
        self.assertNotIn('network_policy', evidence)
        self.assertNotIn('registration_enabled', evidence)

    def test_unknown_gui_cannot_drop_lan_guard(self):
        gui = ET.fromstring('<settings/>')
        options = {'endpoint':'192.168.50.10:20130', 'registration_url':'',
                   'network_policy':'lan-test-v1'}
        with self.assertRaises(ValueError):
            candidate.apply_registration(gui, {'empty_url_settings':[]}, options)


if __name__ == '__main__':
    unittest.main()
