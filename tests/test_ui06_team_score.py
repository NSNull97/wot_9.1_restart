"""UI-06 Results10 in the Domain: a journal the gateway really wrote passes, a stored
journal without the block stays valid, a score that disagrees with the deaths is
refused. Store tests use real isolated SQLite transactions. The contract class
reads the original #717 bytecode as data. No native or UI claim.

tests/fixtures/ui06-results10-from-gateway.json is the output of the gateway test
ui06_results_carry_the_battle_values_into_the_native_fields (a real shell of slot 0
journaled on its ally, slot 2), so this is not a round trip of one coder.
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
from py27_static import disassemble, opcode_table, parse_pyc, records, text
from tests import test_p04d_crew_store as crew_fixture
from tests import test_p06t_mixed_store as previous
from tests import test_p08c_interaction_store as interaction

GATEWAY = (ROOT / "tests/fixtures/ui06-results10-from-gateway.json").read_text(encoding="utf-8")
ORIGINAL = Path("C:/WoT_0.9.1_RU_0717_original/res/scripts")
OPCODES = ROOT / "local/toolchains-py27-20261019/cpython-2.7.3-x86/Lib/opcode.py"
KILLER = 0


def raw(value):
    return canonical(value).decode("utf-8")


class TeamScoreJournal(unittest.TestCase):
    def refuse(self, value):
        with self.assertRaises(TransactionError) as caught:
            results.results_value(raw(value))
        self.assertEqual(str(caught.exception), "INVALID_INPUT")

    def test_the_journal_of_the_gateway_passes_with_its_numbers(self):
        value = results.results_value(GATEWAY)
        row = value["team_score"]["rows"][KILLER]
        self.assertEqual(value["team_score"]["policy"], results.TEAM_SCORE_POLICY)
        self.assertEqual((row["frags"], row["team_kills"], row["team_killer"]), (-1, 1, True))

    def test_a_journal_stored_before_the_block_stays_valid(self):
        value = json.loads(GATEWAY)
        del value["team_score"]
        results.results_value(raw(value))
        del value["interaction_details"]
        results.results_value(raw(value))

    def test_a_score_that_disagrees_with_the_deaths_is_refused(self):
        def poisons():
            yield lambda v: v["team_score"].update(version=2)
            yield lambda v: v["team_score"].update(policy="fake")
            yield lambda v: v["team_score"].update(extra=1)
            yield lambda v: v["team_score"]["rows"].pop()
            yield lambda v: v["team_score"]["rows"].reverse()
            yield lambda v: v["team_score"]["rows"][KILLER].update(frags=0)
            yield lambda v: v["team_score"]["rows"][KILLER].update(frags=True)
            yield lambda v: v["team_score"]["rows"][KILLER].update(team_kills=0)
            yield lambda v: v["team_score"]["rows"][KILLER].update(team_killer=False)
            yield lambda v: v["team_score"]["rows"][KILLER].update(team_killer=1)
            yield lambda v: v["team_score"]["rows"][KILLER].update(team_damage=60001)
            yield lambda v: v["team_score"]["rows"][KILLER].update(team_hits=2)
            yield lambda v: v["team_score"]["rows"][KILLER].update(extra=1)
            yield lambda v: v["team_score"]["rows"][KILLER].pop("frags")
        for poison in poisons():
            value = json.loads(GATEWAY)
            poison(value)
            self.refuse(value)

    def test_a_kill_of_the_enemy_needs_a_plus(self):
        value = json.loads(GATEWAY)
        victim = value["participants"][2]
        victim["team"] = 2
        value["participants"][1]["team"] = 1
        results_row = value["team_score"]["rows"][KILLER]
        results_row.update(frags=1, team_kills=0, team_damage=0, team_hits=0, team_killer=False)
        results.results_value(raw(value))
        results_row.update(frags=-1)
        self.refuse(value)


Base = interaction.InteractionStoreTests


class TeamScoreStoreTests(Base):
    """Only the tests below run, not the predecessor's suite by inheritance."""

    def setUp(self):
        self.enterContext(patch.object(crew_fixture, "TEMP", ROOT / "local/ui06-results-store-tests"))
        previous.MixedStoreTests.setUp(self)

    def score(self, value):
        return dict(version=1, policy=results.TEAM_SCORE_POLICY, rows=[
            dict(vehicle_id=row["vehicle_id"], frags=sum(1 for q in value["participants"]
                     if q["killer_id"] == row["vehicle_id"] and q["vehicle_id"] != row["vehicle_id"]),
                 team_kills=0, team_damage=0, team_hits=0, team_killer=False) for row in value["participants"]])

    def result(self):
        value = interaction.InteractionStoreTests.result(self)
        value["team_score"] = self.score(value)
        return value

    def test_results10_is_stored_and_read_back_with_its_numbers(self):
        finish = self.prepared_finish()
        self.assertEqual(self.send(finish)["status"], "finished")
        stored = json.loads(self.read(self.query())["results_json"])
        self.assertEqual(stored["team_score"], self.result()["team_score"])
        self.assertEqual(self.read(self.query("details-ack:1", "ack"))["status"], "acked")
        self.assertEqual(json.loads(self.read(self.query("details-query:2"))["results_json"])["team_score"], stored["team_score"])

    def test_a_stored_row_without_the_block_reads_back_unchanged(self):
        self.result = lambda: interaction.InteractionStoreTests.result(self)
        finish = self.prepared_finish()
        self.assertEqual(self.send(finish)["status"], "finished")
        self.assertNotIn("team_score", json.loads(self.read(self.query())["results_json"]))


for name in dir(Base):
    if name.startswith("test_"):
        setattr(TeamScoreStoreTests, name, None)
del Base


@unittest.skipUnless(ORIGINAL.is_dir() and OPCODES.is_file(), "original #717 copy absent")
class NativeContract(unittest.TestCase):
    """What the card's design stands on, read from the original bytecode."""

    @staticmethod
    def code(path, name):
        root = parse_pyc((ORIGINAL / path).read_bytes())
        return next(code for qualified, code in records(root) if qualified.endswith(name))

    def instructions(self, path, name):
        table = opcode_table(OPCODES.read_text(encoding="latin-1"))
        return disassemble(self.code(path, name), table)

    def test_update_numbers(self):
        rows = self.instructions("common/constants.pyc", ".ARENA_UPDATE")
        code = self.code("common/constants.pyc", ".ARENA_UPDATE")
        numbers = {}
        for first, second in zip(rows, rows[1:]):
            if first["opname"] == "LOAD_CONST" and second["opname"] == "STORE_NAME":
                numbers[second["value"]] = code["consts"][first["arg"]]
        self.assertEqual((numbers["VEHICLE_STATISTICS"], numbers["TEAM_KILLER"]), (5, 10))

    def test_the_client_prints_any_nonzero_frags_through_str(self):
        names = text(self.code("client/gui/scaleform/playerspanel.pyc", ".getFormattedStrings")["names"])
        self.assertIn("str", names)
        self.assertIn("frags", names)
        rows = self.instructions("client/gui/scaleform/playerspanel.pyc", ".getFormattedStrings")
        values = [row.get("value") for row in rows]
        at = values.index("frags")
        self.assertEqual(rows[at + 1]["opname"], "POP_JUMP_IF_FALSE", "a truth test, not a sign test")

    def test_statistics_row_is_a_pair_and_team_killer_a_bare_id(self):
        self.assertIn("isTeamKiller", text(self.code("client/clientarena.pyc", ".__onTeamKiller")["consts"]))
        self.assertIn("frags", text(self.code("client/clientarena.pyc", ".__vehicleStatisticsAsDict")["consts"]))

    def test_the_panel_paints_only_the_own_team_and_the_minimap_does_not_check(self):
        enemy = self.code("client/gui/battle_control/battle_arena_ctrl.pyc", "EnemyTeamCtx.isTeamKiller")
        self.assertEqual(text(enemy["names"]), ["False"])
        minimap = text(self.code("client/gui/scaleform/minimap.pyc", ".__onTeamKiller")["names"])
        self.assertNotIn("team", minimap)
        self.assertIn("teamKiller", minimap)

    def test_the_results_window_subtracts_tkills_from_kills(self):
        root = parse_pyc((ORIGINAL / "client/gui/scaleform/daapi/view/battleresultswindow.pyc").read_bytes())
        constants = [text(c) for _, code in records(root) for c in code["consts"] if isinstance(c, (str, bytes))]
        self.assertIn("realKills", constants)
        self.assertIn("tkills", constants)


if __name__ == "__main__":
    unittest.main()
