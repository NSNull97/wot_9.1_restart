"""Exercise our passive trace selector; simulated frames are not native evidence."""
import ast
from pathlib import Path
from types import SimpleNamespace
import unittest

SOURCE = Path(__file__).resolve().parents[1] / 'client_patch/sr_interactive.py'
PREFIX = 'scripts/client/gui/Scaleform/daapi/view/lobby/'
TARGETS = (
    (PREFIX + 'customization/VehicleCustomization.py', '_populate', 62),
    (PREFIX + 'hangar/TechnicalMaintenance.py', '_populate', 43),
    (PREFIX + 'hangar/AmmunitionPanel.py', 'showCustomization', 210),
    (PREFIX + 'hangar/AmmunitionPanel.py', 'showTechnicalMaintenance', 207),
)


class WindowTraceTests(unittest.TestCase):
    def setUp(self):
        tree = ast.parse(SOURCE.read_bytes())
        functions = [node for node in tree.body if isinstance(node, ast.FunctionDef)
                     and node.name == 'profile_calls']
        self.assertEqual(len(functions), 1)
        self.events = []
        self.namespace = {'_profile_call_id': 0, '_profile_frames': {}, '_control': None,
                          '_settings': {},
                          'record': lambda event, **fields: self.events.append((event, fields))}
        # Only trusted repository function code, no imported personality or input data.
        exec(compile(ast.Module(body=functions, type_ignores=[]), str(SOURCE), 'exec'), self.namespace)
        self.observe = self.namespace['profile_calls']

    @staticmethod
    def frame(source, method, line=1):
        return SimpleNamespace(f_code=SimpleNamespace(co_filename=source, co_name=method,
                    co_firstlineno=line), f_locals={'self': SimpleNamespace(flashObject=object())},
                    f_lasti=0, f_back=None)

    def test_all_four_original_entries_have_paired_observations(self):
        for source, method, line in TARGETS:
            frame = self.frame(source, method, line)
            self.observe(frame, 'call', None)
            frame.f_lasti = 31
            self.observe(frame, 'return', None)
            start, end = self.events[-2:]
            self.assertEqual(start[0], 'native_unsupported_window_call')
            self.assertEqual(end[0], start[0])
            self.assertEqual(start[1]['call_id'], end[1]['call_id'])
            self.assertEqual(end[1]['source_line'], line)
            self.assertEqual(end[1]['offset'], 31)
            self.assertEqual(end[1]['phase'], 'return')
            self.assertTrue(end[1]['flash_bound'])
        self.assertEqual(self.namespace['_profile_frames'], {})

    def test_owned_wrappers_are_not_reported_as_original_entries(self):
        for method in ('appearance', 'maintenance', 'showCustomization', 'showTechnicalMaintenance'):
            self.observe(self.frame('hangar_capabilities.py', method), 'call', None)
        self.assertEqual(self.events, [])

    def test_unrelated_native_methods_and_similar_paths_are_not_reported(self):
        for source, method, _ in TARGETS:
            self.observe(self.frame(source, 'unrelated_method'), 'call', None)
            self.observe(self.frame('alternate/' + source, method), 'call', None)
        self.assertEqual(self.events, [])

    def test_non_python_call_phases_are_ignored(self):
        for phase in ('c_call', 'c_return', 'c_exception', 'exception'):
            self.observe(self.frame(*TARGETS[0]), phase, None)
        self.assertEqual(self.events, [])

    def test_ammunition_hook_requires_explicit_flag_and_keeps_original_trace(self):
        calls = []
        helper = SimpleNamespace(observe_profile=lambda frame, phase: calls.append((frame, phase)))
        self.namespace['sys'] = SimpleNamespace(modules={'p09d_ammo_ui': helper})
        frame = self.frame(*TARGETS[0])
        self.observe(frame, 'call', None)
        self.assertEqual(calls, [])
        self.namespace['_settings'] = {'enable_p09d_ammo_service': True}
        self.observe(frame, 'call', None)
        self.observe(frame, 'return', None)
        self.assertEqual(calls, [(frame, 'call'), (frame, 'return')])
        self.assertEqual([row[0] for row in self.events], ['native_unsupported_window_call'] * 3)

    def test_ammunition_partial_import_keeps_original_trace_until_observer_exists(self):
        self.namespace['_settings'] = {'enable_p09d_ammo_service': True}
        modules = {}
        self.namespace['sys'] = SimpleNamespace(modules=modules)
        frame = self.frame(*TARGETS[0])
        self.observe(frame, 'call', None)
        helper = SimpleNamespace()
        modules['p09d_ammo_ui'] = helper
        self.observe(frame, 'return', None)
        calls = []
        helper.observe_profile = lambda f, phase: calls.append((f, phase))
        self.observe(frame, 'call', None)
        self.assertEqual(calls, [(frame, 'call')])
        self.assertEqual([row[0] for row in self.events], ['native_unsupported_window_call'] * 3)


if __name__ == '__main__':
    unittest.main()
