"""Function-only harnesses must reproduce the client's scenario initializer."""
import ast
from pathlib import Path
import unittest

from tests import test_interactive_relogin_control as relogin
from tests import test_p04d_crew_control as crew
from tests import test_p09d_ammo_control as ammo


class ScenarioInitializerTests(unittest.TestCase):
    def test_module_and_extracted_function_harnesses_start_disabled(self):
        path = Path(__file__).resolve().parents[1] / 'client_patch/sr_interactive.py'
        tree = ast.parse(path.read_bytes())
        assignments = [node for node in tree.body if isinstance(node, ast.Assign)
                       and any(isinstance(target, ast.Name) and target.id == '_profile13_fight_scenario'
                               for target in node.targets)]
        self.assertEqual(len(assignments), 1)
        self.assertIsNone(ast.literal_eval(assignments[0].value))
        for loader in (relogin.trusted_functions, crew.functions, ammo.functions):
            with self.subTest(loader=loader.__module__):
                namespace = {}
                loader(set(), namespace)
                self.assertIsNone(namespace['_profile13_fight_scenario'])
                scenario = object()
                namespace['_profile13_fight_scenario'] = scenario
                loader(set(), namespace)
                self.assertIs(namespace['_profile13_fight_scenario'], scenario)
