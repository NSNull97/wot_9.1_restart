import unittest
from tools.content0_s5a_scope_profiles import check_projection,FIELDS
class ScopeTests(unittest.TestCase):
    def test_rejects_changed_physics_or_handling(self):
        physics={key:1 for key in FIELDS};handling={'version':1};profile={'definition':{'physics':physics,'handling':handling}}
        row=dict(physics,handling=handling);check_projection(profile,[row])
        for key in FIELDS:
            changed=dict(row);changed[key]=2
            with self.assertRaises(ValueError):check_projection(profile,[changed])
        changed=dict(row,handling={'version':2})
        with self.assertRaises(ValueError):check_projection(profile,[changed])
