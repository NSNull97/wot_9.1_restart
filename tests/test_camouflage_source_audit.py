import unittest

from tools.camouflage_source_audit import matching_fields, net_facts


class CamouflageSourceAuditTests(unittest.TestCase):
    def test_exact_names_do_not_confuse_visual_camouflage(self):
        rows = {"/camouflage[1]/priceFactor[1]": "1.0",
                "/turrets0[1]/turret[1]/invisibilityFactor[1]": "0.88",
                "/camouflageNetBonus[1]": "0.1",
                "/fakeinvisibility[1]": "42"}
        self.assertEqual(matching_fields(rows), [
            {"path": "/camouflageNetBonus[1]", "value": "0.1"},
            {"path": "/turrets0[1]/turret[1]/invisibilityFactor[1]", "value": "0.88"},
        ])

    def test_net_facts_fail_closed_on_changed_delay(self):
        prefix = "/camouflageNet[1]"
        data = {prefix + "/id[1]": 6, prefix + "/script[1]": "CamouflageNet",
                prefix + "/script[1]/weight[1]": 100,
                prefix + "/script[1]/activateWhenStillSec[1]": "3.0"}
        self.assertEqual(net_facts(data)["compact_id"], 1785)
        data[prefix + "/script[1]/activateWhenStillSec[1]"] = "4.0"
        with self.assertRaises(ValueError):
            net_facts(data)


if __name__ == "__main__":
    unittest.main()
