"""CLIENT-PERF-01: the global native-call profiler of sr_interactive only in diagnostic runs.

The rule is extracted from our trusted source (as test_interactive_primitive does);
the personality itself is not imported. Native fps and the hangar behaviour are
checked on the owner's clients, not here.
"""
import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'client_patch/sr_interactive.py'


def source_tree():
    return ast.parse(SOURCE.read_bytes(), filename=str(SOURCE))


def load(name):
    functions = [node for node in source_tree().body if isinstance(node, ast.FunctionDef) and node.name == name]
    if len(functions) != 1:
        raise AssertionError('expected one function ' + name)
    namespace = {}
    exec(compile(ast.Module(body=functions, type_ignores=[]), str(SOURCE), 'exec'), namespace)
    return namespace[name]


class NativeCallTraceRule(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.wanted = staticmethod(load('native_call_trace_wanted'))

    def test_ordinary_play_goes_without_the_profiler(self):
        owner_install = {'test_control': None, 'capture_ui_passive': False, 'trace_native_calls': False,
                         'enable_profile13_battle': True, 'enable_crew_any': True, 'enable_p09d_ammo_service': True,
                         'trace_pose_10hz': True}
        self.assertIsNone(self.wanted(owner_install))
        self.assertIsNone(self.wanted({}), 'an install from before the flag')

    def test_diagnostic_runs_keep_it_and_say_why(self):
        self.assertEqual('test_control', self.wanted({'test_control': 'D:/local/x/control.json'}))
        self.assertEqual('capture_ui_passive', self.wanted({'capture_ui_passive': True}))
        self.assertEqual('trace_native_calls', self.wanted({'trace_native_calls': True}))

    def test_init_installs_the_profiler_only_under_the_rule(self):
        init = [node for node in source_tree().body if isinstance(node, ast.FunctionDef) and node.name == 'init'][0]
        calls = [node for node in ast.walk(init) if isinstance(node, ast.Call)
                 and isinstance(node.func, ast.Attribute) and node.func.attr == 'setprofile']
        self.assertEqual(1, len(calls))
        guarded = [node for node in ast.walk(init) if isinstance(node, ast.If)
                   and any(call is inner for inner in ast.walk(node) for call in calls)]
        self.assertEqual(1, len(guarded), 'sys.setprofile(profile_calls) must sit under the rule')
        self.assertIn('reason', ast.unparse(guarded[0].test))

    def test_a_non_boolean_setting_is_refused_at_load(self):
        self.assertIn("if type(_settings.get('trace_native_calls', False)) is not bool:", SOURCE.read_text())


class PrepareFlag(unittest.TestCase):
    def test_prepare_writes_the_flag_as_a_boolean(self):
        text = (ROOT / 'tools/interactive_client.py').read_text(encoding='utf-8')
        self.assertIn("prep.add_argument('--trace-native-calls', action='store_true',", text)
        self.assertIn("'trace_native_calls':bool(getattr(args, 'trace_native_calls', False)),", text)


if __name__ == '__main__':
    unittest.main()
