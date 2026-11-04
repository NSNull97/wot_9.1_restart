"""UI-04 Results9 in the Domain: a journal the gateway really wrote passes, a stored
Results8 stays valid, a ledger that disagrees is refused. Store tests use real
isolated SQLite transactions; no native or UI claim.

tests/fixtures/results9-from-gateway.json is the output of the gateway test
ui04_ledger_of_a_real_shell_fills_totals_and_the_row_of_its_target (a real shell,
a third vehicle holding the spot credit), so this is not a round trip of one coder.
"""
from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
import p08c_battle_results as results
from game_profile_tx import TransactionError
from p09d_ammo_projection import canonical
from tests import test_p04d_crew_store as crew_fixture
from tests import test_p06t_mixed_store as previous
from tests import test_p08c_interaction_store as interaction

GATEWAY = (ROOT / "tests/fixtures/results9-from-gateway.json").read_text(encoding="utf-8")
ALLY, ENEMY = 2, 1


def raw(value):
    return canonical(value).decode("ascii")


class ValidatorTests(unittest.TestCase):
    def refuse(self, value):
        with self.assertRaises(TransactionError) as caught:
            results.results_value(raw(value))
        self.assertEqual(caught.exception.code, "INVALID_INPUT")

    def test_the_journal_the_gateway_wrote_passes_and_keeps_its_numbers(self):
        value = results.results_value(GATEWAY)
        row = value["ledger"]["rows"][ALLY]
        self.assertEqual(value["ledger"]["policy"], results.LEDGER_POLICY)
        self.assertEqual(row["assist_spot"], value["participants"][ENEMY]["damage_received"])
        target = value["interaction_details"]["rows"][ALLY]["targets"][0]
        self.assertEqual((target["vehicle_id"], target["damage_assisted_radio"]),
                         (value["participants"][ENEMY]["vehicle_id"], row["assist_spot"]))

    def old_journal(self):
        value = json.loads(GATEWAY)
        del value["ledger"]
        targets = value["interaction_details"]["rows"][ALLY]["targets"]
        for target in targets:
            target["damage_assisted_radio"] = 0
        return value

    def test_a_journal_stored_before_the_ledger_stays_valid(self):
        results.results_value(raw(self.old_journal()))
        value = self.old_journal()
        del value["interaction_details"]
        results.results_value(raw(value))

    def test_assist_numbers_without_the_ledger_are_refused(self):
        value = json.loads(GATEWAY)
        del value["ledger"]
        self.refuse(value)

    def test_a_ledger_that_disagrees_is_refused(self):
        def poisons():
            yield lambda v: v.pop("interaction_details")
            yield lambda v: v["ledger"].update(version=2)
            yield lambda v: v["ledger"].update(policy="fake")
            yield lambda v: v["ledger"].update(extra=1)
            yield lambda v: v["ledger"]["rows"].pop()
            yield lambda v: v["ledger"]["rows"].reverse()
            yield lambda v: v["ledger"]["rows"][ALLY].update(assist_spot=1)
            yield lambda v: v["ledger"]["rows"][ALLY].update(assist_track=1)
            yield lambda v: v["ledger"]["rows"][ALLY].update(extra=1)
            yield lambda v: v["ledger"]["rows"][ALLY].update(blocked=1)
            yield lambda v: v["ledger"]["rows"][ALLY].update(potential_received=-1)
            yield lambda v: v["ledger"]["rows"][ALLY].update(burned=1)
            yield lambda v: v["ledger"]["rows"][ALLY].update(blocked=True)
        for poison in poisons():
            value = json.loads(GATEWAY)
            poison(value)
            self.refuse(value)

    def test_assist_on_an_ally_is_refused(self):
        value = json.loads(GATEWAY)
        value["participants"][ENEMY]["team"] = 1
        value["participants"][0]["team"] = 2
        self.refuse(value)

    def test_an_assist_only_target_is_a_fact(self):
        value = json.loads(GATEWAY)
        target = value["interaction_details"]["rows"][ALLY]["targets"][0]
        target["spotted"] = 0
        value["interaction_details"]["rows"][0]["targets"][0]["spotted"] = 1
        results.results_value(raw(value))


Base = interaction.InteractionStoreTests


class LedgerStoreTests(Base):
    """Only the tests below run, not the predecessor's suite by inheritance."""

    def setUp(self):
        self.enterContext(patch.object(crew_fixture, "TEMP", ROOT / "local/ui04-results-store-tests"))
        previous.MixedStoreTests.setUp(self)

    def result(self):
        value = interaction.InteractionStoreTests.result(self)
        target = value["interaction_details"]["rows"][0]["targets"][0]
        target["damage_assisted_radio"], target["damage_assisted_track"] = 11, 7
        value["ledger"] = dict(version=1, policy=results.LEDGER_POLICY, rows=[
            dict(vehicle_id=value["participants"][0]["vehicle_id"], blocked=300, potential_received=420,
                 assist_spot=11, assist_track=7, burned=40),
            dict(vehicle_id=value["participants"][1]["vehicle_id"], blocked=0, potential_received=0,
                 assist_spot=0, assist_track=0, burned=0)])
        return value

    def test_results9_is_stored_and_read_back_with_its_numbers(self):
        finish = self.prepared_finish()
        self.assertEqual(self.send(finish)["status"], "finished")
        response = self.read(self.query())
        self.assertEqual(response["status"], "found")
        stored = json.loads(response["results_json"])
        self.assertEqual(stored["ledger"], self.result()["ledger"])
        self.assertEqual(self.read(self.query("details-ack:1", "ack"))["status"], "acked")
        self.assertEqual(json.loads(self.read(self.query("details-query:2"))["results_json"])["ledger"], stored["ledger"])

    def test_a_stored_results8_row_reads_back_unchanged(self):
        self.result = lambda: interaction.InteractionStoreTests.result(self)
        finish = self.prepared_finish()
        self.assertEqual(self.send(finish)["status"], "finished")
        stored = json.loads(self.read(self.query())["results_json"])
        self.assertNotIn("ledger", stored)


for name in dir(Base):
    if name.startswith("test_"):
        setattr(LedgerStoreTests, name, None)
del Base


if __name__ == "__main__":
    unittest.main()
