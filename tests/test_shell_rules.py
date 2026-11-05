"""SHELL-CFG: profile layers -> immutable rules snapshot (tools/shell_rules.py)."""
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import shell_rules as sr  # noqa: E402


class Snapshot(unittest.TestCase):
    def test_committed_snapshot_and_pins_are_current(self):
        raw = sr.build_snapshot()
        self.assertEqual(sr.SNAPSHOT.read_bytes(), raw)
        self.assertEqual(sr.PINS.read_bytes(), sr.rust_pins(raw))
        doc = json.loads(raw)
        self.assertEqual((doc['schema'], doc['config_version'], doc['profile']), ('wot091-shell-rules.v1', 1, 'classic_plus'))
        self.assertEqual([layer['name'] for layer in doc['layers']], list(sr.LAYERS))

    def test_values_are_the_former_lab_constants(self):
        rules = json.loads(sr.build_snapshot())['rules']
        value = lambda *path: _get(rules, path)['value']
        self.assertEqual([value('families', f, 'normalization_deg') for f in ('armor_piercing', 'armor_piercing_cr', 'hollow_charge', 'high_explosive')],
                         [5.0, 2.0, 0.0, 0.0])
        self.assertEqual([value('families', f, 'ricochet_deg') for f in ('armor_piercing', 'armor_piercing_cr', 'hollow_charge', 'high_explosive')],
                         [70.0, 70.0, 85.0, None])
        self.assertEqual((value('caliber', 'normalization_ratio'), value('caliber', 'normalization_multiplier'), value('caliber', 'no_ricochet_ratio')),
                         (2.0, 1.4, 3.0))
        self.assertEqual((value('falloff', 'full_power_until_m'), value('falloff', 'linear_span_m')), (100.0, 400.0))
        self.assertEqual((value('high_explosive', 'damage_factor'), value('high_explosive', 'armor_factor')), (0.5, 1.1))

    def test_canonical_bytes(self):
        raw = sr.build_snapshot()
        self.assertTrue(raw.endswith(b'\n') and b'\r' not in raw and b' ' not in raw.split(b'"source"')[0])


def _get(tree, path):
    for key in path:
        tree = tree[key]
    return tree


class Layers(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        for path in sr.DIR.glob('*.json'):
            if path.name != 'snapshot.json':
                shutil.copy(path, self.dir / path.name)

    def tearDown(self):
        self.tmp.cleanup()

    def layer(self, name, rules):
        (self.dir / (name + '.json')).write_text(json.dumps({'layer': name, 'rules': rules}), encoding='utf-8')

    def leaf(self, value, status='experimental'):
        return {'value': value, 'status': status, 'source': 'test'}

    def test_later_layer_replaces_a_leaf_and_changes_the_hash(self):
        base = sr.build_snapshot(self.dir)
        self.layer('classic_plus', {'families': {'hollow_charge': {'ricochet_deg': self.leaf(80.0)}}})
        changed = sr.build_snapshot(self.dir)
        rules = json.loads(changed)['rules']
        self.assertEqual(rules['families']['hollow_charge']['ricochet_deg'], self.leaf(80.0))
        self.assertEqual(rules['families']['armor_piercing']['ricochet_deg']['value'], 70.0)
        self.assertNotEqual(sr.sha(base), sr.sha(changed))
        self.layer('historical_0_9_1', {'families': {'hollow_charge': {'ricochet_deg': self.leaf(84.0, 'verified_091')}}})
        rules = json.loads(sr.build_snapshot(self.dir))['rules']
        self.assertEqual(rules['families']['hollow_charge']['ricochet_deg']['value'], 80.0, 'classic_plus is after historical')

    def test_closed_schema_refusals(self):
        bad_layers = [
            ('classic_plus', {'caliber': {'extra': self.leaf(1.0)}}),
            ('classic_plus', {'caliber': {'normalization_ratio': self.leaf(0.5)}}),
            ('classic_plus', {'caliber': {'normalization_ratio': {'value': 2.0, 'status': 'guess', 'source': 'x'}}}),
            ('classic_plus', {'caliber': {'normalization_ratio': {'value': 2.0, 'status': 'test_lab'}}}),
            ('classic_plus', {'families': {'armor_piercing': {'caliber_rules': self.leaf(1)}}}),
            ('classic_plus', {'families': {'armor_piercing': {'normalization_deg': self.leaf(None)}}}),
            ('classic_plus', {'laws': {'direct': self.leaf('made-up-law')}}),
            ('shell_definition', {'caliber': {'normalization_ratio': self.leaf(2.5)}}),
            ('game_mode', {'falloff': {'linear_span_m': self.leaf(300.0)}}),
        ]
        for name, rules in bad_layers:
            with self.subTest(layer=name, rules=rules):
                self.setUp()
                self.layer(name, rules)
                with self.assertRaises(sr.RulesError):
                    sr.build_snapshot(self.dir)

    def test_profile_order_and_identity_are_fixed(self):
        profile = json.loads((self.dir / 'profile.json').read_text(encoding='utf-8'))
        profile['layers'] = list(reversed(profile['layers']))
        (self.dir / 'profile.json').write_text(json.dumps(profile), encoding='utf-8')
        with self.assertRaises(sr.RulesError):
            sr.build_snapshot(self.dir)

    def test_incomplete_defaults_are_refused(self):
        defaults = json.loads((self.dir / 'server_defaults.json').read_text(encoding='utf-8'))
        del defaults['rules']['high_explosive']
        (self.dir / 'server_defaults.json').write_text(json.dumps(defaults), encoding='utf-8')
        with self.assertRaises(sr.RulesError):
            sr.build_snapshot(self.dir)


if __name__ == '__main__':
    unittest.main()
