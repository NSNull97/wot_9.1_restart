"""LATE-BOTS v2: isolated SQLite lineage, with authored gateway outcome facts."""
from copy import deepcopy
import json
import os
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_p08c_late_results as fixtures
from test_p08c_late_results import Scenario, ACCOUNTS
from p09e_research_catalog import load_catalog
from p08c_late_results import BOT_DATABASE_BASE, BOT_POLICY_NAME, POLICY_NAME, LateResults, canonical, vehicle_id


class BotScenario(Scenario):
    places = 30
    humans = 1

    def final(self, slot, hp=90):
        final = super().final(slot, hp)
        final["terminal_state"]["roster_size"] = self.places
        return final

    def bot_rows(self):
        used = {self.public(self.stores[i])["native_database_id"] for i in range(self.humans)}
        rows = []
        for ordinal, slot in enumerate(range(self.humans, self.places)):
            database = BOT_DATABASE_BASE + ordinal
            while database in used:
                database += 1
            used.add(database)
            rows.append(dict(slot=slot, vehicle_id=vehicle_id(slot), team=slot % 2 + 1, native_database_id=database))
        return rows

    def result(self, finals, large=False):
        value = super().result(finals)
        for slot, participant in enumerate(value["participants"]):
            participant["team"] = slot % 2 + 1
        for bot in self.bot_rows():
            value["participants"].append(dict(vehicle_id=bot["vehicle_id"], account_dbid=bot["native_database_id"], name="Bot-%02d" % (bot["slot"] - self.humans + 1),
                team=bot["team"], type_compact_descr=3329, health=90, shots=0, direct_hits=0, piercings=0, damage_dealt=0, damage_received=0,
                kills=0, capture_points=0, dropped_capture_points=0, mileage_metres=0, life_time=0, killer_id=0, death_reason=-1, premature_leave=False))
        if large:
            # 30x29 bounded distinct interaction facts give a realistic large
            # roster payload and expose the former 32 KiB human-count limit.
            rows = []
            for actor in value["participants"]:
                targets = [dict(vehicle_id=target["vehicle_id"], spotted=0, death_reason=-1, direct_hits=0, explosion_hits=0,
                    piercings=0, damage_dealt=0, damage_assisted_track=0, damage_assisted_radio=0, crits=1, fire=0)
                    for target in value["participants"] if target is not actor]
                rows.append(dict(attacker_vehicle_id=actor["vehicle_id"], targets=sorted(targets, key=lambda v: v["vehicle_id"])))
            # Owner lost HP after leaving: attach the same amount of damage to
            # a bot interaction so the server's result cross-check stays real.
            damage = value["participants"][0]["damage_received"]
            if damage:
                shooter = value["participants"][1]
                shooter.update(shots=1, direct_hits=1, piercings=1, damage_dealt=damage)
                hit = next(t for t in rows[1]["targets"] if t["vehicle_id"] == value["participants"][0]["vehicle_id"])
                hit.update(direct_hits=1, piercings=1, damage_dealt=damage)
            value["interaction_details"] = dict(version=1, policy="test_lab.authoritative-interactions.v1", spotting_policy=None, rows=rows)
        return value

    def append_request(self, finals, result=None, slot=0, poison=None):
        # The shared scenario constructs both source links, then v2 selects
        # the real humans only; BOT-01 rows never contain source credentials.
        all_finals = finals + [self.final(1)] * (2 - len(finals))
        request = super().append_request(all_finals, result or self.result(finals), slot)
        seal = json.loads(request["seal_json"])
        seal["actors"] = seal["actors"][:self.humans]
        for actor in seal["actors"]:
            actor["team"] = actor["slot"] % 2 + 1
        seal.update(version=2, policy=BOT_POLICY_NAME, bots=self.bot_rows())
        if poison:
            poison(seal)
        request["seal_json"] = canonical(seal).decode("utf8")
        return request


class LateBotsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Explicit path lets an isolated checkout use an existing read-only
        # local seed without copying the sizeable evidence tree.
        if os.environ.get("WOT_LATE_RESULTS_SEED"):
            fixtures.SEED = Path(os.environ["WOT_LATE_RESULTS_SEED"])
        seed = json.loads(fixtures.SEED.read_bytes())
        cls.catalog = load_catalog(seed["original"])

    def fixture(self, loss=False):
        value = BotScenario(self.catalog, loss)
        self.addCleanup(value.close)
        return value

    def test_1_plus_29_late_damage_and_large_roster_append_without_inventory_writes(self):
        for loss in (False, True):
            with self.subTest(loss=loss):
                f = self.fixture(loss)
                released = f.final(0, 90)
                self.assertEqual(f.finish(0, released)["status"], "finished")
                final = f.final(0, 50)
                result = f.result([final], large=True)
                self.assertGreater(len(canonical(result)), 32768)
                request = f.append_request([final], result)
                self.assertGreater(len(request["seal_json"].encode("utf8")), 32768)
                before = f.old_tables()
                reply = f.call(request)
                self.assertEqual(reply["status"], "appended", reply)
                self.assertEqual(f.old_tables(), before)
                self.assertEqual(f.call(request), dict(reply, replayed=True))
                self.assertEqual(len(LateResults(f.stores[0]).pending(ACCOUNTS[0], 1)), 1)
                _, found = f.query()
                self.assertEqual(found["status"], "found")
                self.assertEqual(len(json.loads(found["results_json"])["participants"]), 30)
                self.assertEqual(f.stores[0].connection.execute("SELECT COUNT(*) FROM p08c_late_result").fetchone()[0], 1)
                self.assertTrue(f.query("ack")[1]["acked"])
                self.assertEqual(f.old_tables(), before)

    def test_v2_rejects_tampering_and_additional_shots_without_writes(self):
        for loss in (False, True):
            with self.subTest(loss=loss):
                f = self.fixture(loss)
                released = f.final(0, 70)
                f.finish(0, released)
                before = f.old_tables()
                final = f.final(0, 50)
                poisons = {
                    "wrong policy": lambda s: s.update(policy=POLICY_NAME),
                    "v1 with bots": lambda s: s.update(version=1),
                    "missing bot": lambda s: s["bots"].pop(),
                    "wrong slot": lambda s: s["bots"][0].update(slot=2),
                    "wrong identity": lambda s: s["bots"][0].update(native_database_id=BOT_DATABASE_BASE+4),
                    "extra account": lambda s: s["bots"][0].update(account_id=ACCOUNTS[1]),
                    "bool slot": lambda s: s["bots"][0].update(slot=True),
                    "wrong vehicle": lambda s: s["bots"][0].update(vehicle_id=vehicle_id(2)),
                    "wrong team": lambda s: s["bots"][0].update(team=1),
                }
                for name, poison in poisons.items():
                    with self.subTest(poison=name):
                        reply = f.call(f.append_request([final], poison=poison))
                        self.assertEqual(reply["status"], "rejected", reply)
                        self.assertEqual(f.old_tables(), before)
                more_shots = deepcopy(final)
                loaded = next(i for i, row in enumerate(more_shots["remaining_ammunition"]) if row["count"] > 0)
                more_shots["remaining_ammunition"][loaded]["count"] -= 1
                more_shots["fired_ammunition"][loaded]["count"] += 1
                reply = f.call(f.append_request([more_shots]))
                self.assertEqual((reply["status"], reply["code"]), ("rejected", "LATE_ACTOR_STATE_CHANGED"))
                self.assertEqual(f.old_tables(), before)
                healed = f.final(0, 80)
                reply = f.call(f.append_request([healed]))
                self.assertEqual((reply["status"], reply["code"]), ("rejected", "LATE_ACTOR_STATE_CHANGED"))
                self.assertEqual(f.old_tables(), before)
                self.assertEqual(f.call(f.append_request([final]))["status"], "appended")

    def test_two_departed_owners_share_one_seal_and_bots_get_no_records(self):
        f = self.fixture(True)
        f.humans = 2
        f.places = 6
        releases = [f.final(0, 90), f.final(1, 90)]
        for slot, value in enumerate(releases):
            self.assertEqual(f.finish(slot, value)["status"], "finished")
        finals = [f.final(0, 60), f.final(1, 70)]
        result = f.result(finals)
        before = f.old_tables()
        for slot in range(2):
            reply = f.call(f.append_request(finals, result, slot=slot))
            self.assertEqual(reply["status"], "appended", reply)
        self.assertEqual(f.old_tables(), before)
        c = f.stores[0].connection
        self.assertEqual(c.execute("SELECT COUNT(*) FROM p08c_late_seal").fetchone()[0], 1)
        self.assertEqual(c.execute("SELECT COUNT(*) FROM p08c_late_result").fetchone()[0], 2)
        self.assertEqual({r[0] for r in c.execute("SELECT account_id FROM p08c_late_result")}, set(ACCOUNTS))

    def test_v1_still_rejects_post_finish_damage(self):
        f = Scenario(self.catalog)
        self.addCleanup(f.close)
        released = [f.final(0, 90), f.final(1)]
        f.finish(0, released[0])
        final = [f.final(0, 50), f.final(1)]
        reply = f.call(f.append_request(final))
        self.assertEqual((reply["status"], reply["code"]), ("rejected", "LATE_ACTOR_STATE_CHANGED"))


if __name__ == "__main__":
    unittest.main()
