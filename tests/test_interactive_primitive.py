"""Pure diagnostic serializer boundaries; this is not native GUI compatibility.

Extract only our trusted source function so tests never import the personality,
open preferences/traces or require fake BigWorld services. Python 2 string names
are mapped explicitly to their Python 3 equivalents; native compilation and GUI
regression remain separate checks.
"""
import ast
import json
from pathlib import Path
import unittest


SOURCE = Path(__file__).resolve().parents[1] / 'client_patch/sr_interactive.py'


def load_primitive():
    module = ast.parse(SOURCE.read_bytes(), filename=str(SOURCE))
    functions = [node for node in module.body if isinstance(node, ast.FunctionDef)
                 and node.name == 'primitive']
    if len(functions) != 1:
        raise AssertionError('expected one original project diagnostic function')
    namespace = {'json': json, 'long': int, 'str': bytes, 'unicode': str,
                 'basestring': (str, bytes)}
    code = compile(ast.Module(body=functions, type_ignores=[]), str(SOURCE), 'exec')
    exec(code, namespace)  # Trusted repository source, never client/network data.
    return namespace['primitive']


class PrimitiveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.convert = staticmethod(load_primitive())

    def assert_truncated(self, value, **kwargs):
        result = self.convert(value, **kwargs)
        self.assertEqual({'truncated': True}, result)
        self.assertEqual({'truncated': True}, json.loads(json.dumps(result)))

    def test_small_native_values_are_preserved_and_utf8_keys_remain_strings(self):
        value = {b'profile': {b'name': '\u0401\u0436'.encode('utf8'), b'battles': 0},
                 b'flags': (True, None, 1.5)}
        expected = {'profile': {'name': '\u0401\u0436', 'battles': 0}, 'flags': [True, None, 1.5]}
        self.assertEqual(expected, self.convert(value))
        self.assertEqual(expected, json.loads(json.dumps(self.convert(value))))
        self.assertIsInstance(value[b'flags'], tuple)  # no mutation of GUI data

    def test_budget_exhausted_on_first_dict_key_is_an_explicit_marker(self):
        # The old function used primitive(key) == {'truncated': True} as a key.
        self.assert_truncated({b'name': b'value'}, budget=[1])

    def test_nested_budget_exhaustion_propagates_without_unhashable_key(self):
        self.assert_truncated({b'awards': [{b'name': b'a'}, {b'name': b'b'}]}, budget=[4])

    def test_depth_boundary_is_enforced_for_nested_dicts(self):
        at_limit = 7
        for _ in range(8):
            at_limit = {b'next': at_limit}
        self.assertNotEqual({'truncated': True}, self.convert(at_limit))
        self.assert_truncated({b'next': at_limit})

    def test_node_budget_stops_traversal_after_exhaustion(self):
        class CountedList(list):
            visits = 0

            def __iter__(self):
                for item in list.__iter__(self):
                    self.visits += 1
                    yield item

        value = CountedList(range(256))
        self.assert_truncated(value, budget=[2])
        self.assertLessEqual(value.visits, 2)

    def test_oversized_dict_key_cannot_become_an_unhashable_marker(self):
        self.assert_truncated({b'x' * 4097: 1})

    def test_encoded_byte_budget_counts_escaped_unicode(self):
        value = ['\u0401' * 4096 for _ in range(3)]
        self.assert_truncated(value)
        result = self.convert(['\u0401' * 4096])
        self.assertEqual(['\u0401' * 4096], result)
        self.assertLessEqual(len(json.dumps(result, ensure_ascii=True)), 48 * 1024)

    def test_low_byte_budget_cannot_overflow_the_native_trace_record(self):
        self.assert_truncated({b'name': b'value'}, budget=[1024, 8])
        self.assert_truncated({}, budget=[1024, 1])
        self.assert_truncated([], budget=[1024, 1])

    def test_existing_container_width_limit_remains_explicit(self):
        self.assertEqual({'unsupported_type': 'list'}, self.convert(list(range(257))))


if __name__ == '__main__':
    unittest.main()
