"""One-shot local login permission shape; no mock native-game acceptance."""
import ast
from pathlib import Path
import unittest


class SharedControlTests(unittest.TestCase):
    def test_only_explicit_shared_install_accepts_login_only_control(self):
        source = Path(__file__).resolve().parents[1] / 'client_patch/sr_interactive.py'
        tree = ast.parse(source.read_bytes())
        functions = [node for node in tree.body if isinstance(node, ast.FunctionDef)
                     and node.name == 'shared_login_control']
        self.assertEqual(len(functions), 1)
        namespace = {}
        exec(compile(ast.Module(body=functions, type_ignores=[]), str(source), 'exec'), namespace)
        check = namespace['shared_login_control']
        control = {'username': 'owned@example.invalid', 'password': 'unit-only', 'submit_via': 'python'}
        self.assertTrue(check(control, {'enable_shared_lab': True}))
        for settings in ({}, {'enable_shared_lab': False}, {'enable_shared_lab': 1}):
            self.assertFalse(check(control, settings))
        for extra in ('quit_after_seconds', 'probe_map_drive', 'screenshot_when', 'ui_scenario'):
            self.assertFalse(check(dict(control, **{extra: None}), {'enable_shared_lab': True}))
        self.assertFalse(check(dict(control, submit_via='flash'), {'enable_shared_lab': True}))


if __name__ == '__main__':
    unittest.main()
