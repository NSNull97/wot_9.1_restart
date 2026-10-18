"""Pure P06T Results8 validator regression; no SQLite/native setup required."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from p06t_ammo_loss_store import validate_request
from p09d_ammo_projection import canonical
from game_profile_tx import TransactionError


class P06TResultsValidatorTests(unittest.TestCase):
    def test_bounded_module_and_fire_facts_are_accepted_and_overflow_is_rejected(self):
        vectors = json.loads((ROOT / "tests/fixtures/p06t-ammo-loss-writer-vectors.json").read_bytes())
        request = deepcopy(next(v["request"] for v in vectors["vectors"]
                               if v["request"].get("operation") == "finish"))
        result = json.loads(request["results_json"])
        own, peer = result["participants"]
        own["damage_received"] = 7
        peer["damage_received"] = 7
        peer["kills"] = 1
        result["interaction_details"] = {
            "version": 1,
            "policy": "test_lab.authoritative-interactions.v1",
            "spotting_policy": "test_lab.p08c.first-visible-enemy-lowest-slot.v1",
            "rows": [
                {"attacker_vehicle_id": own["vehicle_id"], "targets": [{
                    "vehicle_id": peer["vehicle_id"], "spotted": 1, "death_reason": -1,
                    "direct_hits": 1, "explosion_hits": 0, "piercings": 1, "damage_dealt": 7,
                    "damage_assisted_track": 0, "damage_assisted_radio": 0, "crits": 0, "fire": 0,
                }]},
                {"attacker_vehicle_id": peer["vehicle_id"], "targets": [{
                    "vehicle_id": own["vehicle_id"], "spotted": 1, "death_reason": 0,
                    "direct_hits": 1, "explosion_hits": 0, "piercings": 1, "damage_dealt": 7,
                    "damage_assisted_track": 0, "damage_assisted_radio": 0, "crits": 1, "fire": 1,
                }]},
            ],
        }
        request["results_json"] = canonical(result).decode("ascii")
        parsed = validate_request(request, request["account_id"])
        accepted = json.loads(parsed["results_json"])
        target = accepted["interaction_details"]["rows"][1]["targets"][0]
        self.assertEqual((target["crits"], target["fire"]), (1, 1))
        for field, limit in (("crits", 193), ("fire", 11)):
            poisoned = deepcopy(request)
            value = json.loads(poisoned["results_json"])
            value["interaction_details"]["rows"][1]["targets"][0][field] = limit
            poisoned["results_json"] = canonical(value).decode("ascii")
            with self.assertRaises(TransactionError) as caught:
                validate_request(poisoned, poisoned["account_id"])
            self.assertEqual(caught.exception.code, "INVALID_INPUT")


if __name__ == "__main__":
    unittest.main()
