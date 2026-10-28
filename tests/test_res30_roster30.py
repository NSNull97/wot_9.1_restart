"""RES-30: Domain result journal, terminal, loss event and late seal bounds for
battles of 7..30 actors. Real isolated profile13 SQLite store (P08B/P08C test
chain); one owner + 29 SYNTHETIC rows shaped like BOT-01 bots (no account)."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from tests import test_p08b_battle_store as base_store
from tests import test_p08c_battle_results as previous
from tests import test_p06t_terminal as terminal_tests
from p08b_battle_store import MAX_PARTICIPANTS, MAX_RESULT_BYTES, MAX_RESULT_BYTES_LEGACY, MAX_RESULT_REQUEST, result_budget
from p08c_battle_results import ResultsStore, canonical, results_value
from p06t_ammo_loss_store import _event, MAX_BATTLE_SHOTS, MAX_DEVICE_SEQUENCE
import p08c_late_results as late
from game_profile_tx import TransactionError

BOT_DATABASE = 0x7F000000


def vehicle_id(slot):
    # Gateway wire::vehicle_id for every native/SPAWN-15 slot.
    return 0x09100003 + 2 * slot if slot < 2 else 0x09110003 + 2 * (slot - 2)


def roster(owner, n):
    """Owner row in slot 0 (team 1) + n-1 bot rows; the owner destroyed slot 1."""
    rows = [dict(owner, vehicle_id=vehicle_id(0), kills=1, damage_dealt=90, direct_hits=1, piercings=1)]
    for slot in range(1, n):
        rows.append(dict(owner, vehicle_id=vehicle_id(slot), account_dbid=BOT_DATABASE + slot, name="Bot-%02d" % slot,
            team=1 + slot % 2, type_compact_descr=17, health=90, shots=0, direct_hits=0, piercings=0, damage_dealt=0,
            damage_received=0, kills=0, capture_points=0, dropped_capture_points=0, killer_id=0, death_reason=-1))
    rows[1].update(health=0, damage_received=90, killer_id=vehicle_id(0), death_reason=0, life_time=70)
    return rows


class Roster30ResultsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        base_store.BattleStoreTests.setUpClass.__func__(cls)

    activate = previous.ResultsTests.activate
    profile = previous.ResultsTests.profile
    public = previous.ResultsTests.public
    state = previous.ResultsTests.state
    old_request = previous.ResultsTests.old_request
    request = previous.ResultsTests.request
    call = previous.ResultsTests.call
    start = previous.ResultsTests.start
    reject = previous.ResultsTests.reject
    setUp = previous.ResultsTests.setUp
    finished = previous.ResultsTests.finished
    results_request = previous.ResultsTests.results_request
    send = previous.ResultsTests.send
    base_result = previous.ResultsTests.result

    rows = MAX_PARTICIPANTS

    def result(self):
        value = self.base_result()
        value["participants"] = roster(value["participants"][0], self.rows)
        return value

    def raw(self, value=None):
        return canonical(self.result() if value is None else value).decode("ascii")

    def test_roster30_one_owner_and_29_rows_store_only_owner(self):
        accounts = self.store.connection.execute("SELECT COUNT(*) FROM game_snapshot").fetchone()[0]
        receipt = self.finished(); before = deepcopy(self.profile())
        self.assertEqual(len(self.result()["participants"]), 30)
        self.assertGreater(len(self.raw()), MAX_RESULT_BYTES_LEGACY // 8)
        # Only the requesting owner's row is journaled; bots get no account data.
        self.assertEqual(self.store.connection.execute("SELECT COUNT(*) FROM p08c_result").fetchone()[0], 1)
        self.assertEqual(self.store.connection.execute("SELECT account_id FROM p08c_result").fetchone()[0], self.account)
        request = self.results_request(reservation=receipt); response = self.send(request)
        self.assertEqual((response["status"], response["acked"]), ("stored", False))
        self.assertEqual(json.loads(response["results_json"])["participants"], self.result()["participants"])
        self.assertEqual(self.send(request), dict(response, replayed=True))
        # Re-entry: a reopened store reads, acknowledges and replays without error.
        self.store.close(); self.store = ResultsStore(self.database, self.catalog)
        query = self.results_request("query"); self.assertEqual(self.send(query)["results_json"], response["results_json"])
        ack = self.results_request("ack"); acked = self.send(ack); self.assertTrue(acked["acked"])
        self.assertEqual(self.send(ack), dict(acked, replayed=True))
        self.assertEqual(self.profile(), before)
        self.assertEqual(self.store.connection.execute("SELECT COUNT(*) FROM game_snapshot").fetchone()[0], accounts)
        self.assertFalse(any(self.store.connection.execute("SELECT 1 FROM game_snapshot WHERE account_id LIKE 'bot01:%'").fetchall()))

    def test_roster30_every_size_and_bounds(self):
        owner = self.base_result()["participants"][0]
        for n in range(2, MAX_PARTICIPANTS + 1):
            value = dict(self.base_result(), participants=roster(owner, n))
            self.assertEqual(len(results_value(self.raw(value))["participants"]), n)
        too_many = dict(self.base_result(), participants=roster(owner, 31))
        with self.assertRaises(TransactionError): results_value(self.raw(too_many))
        value = self.result(); value["participants"][0]["kills"] = 29; results_value(self.raw(value))
        value["participants"][0]["kills"] = 30
        with self.assertRaises(TransactionError): results_value(self.raw(value))

    def test_roster30_legacy_rows_keep_32k_and_roster30_gets_256k(self):
        self.assertEqual((result_budget(6), result_budget(7), result_budget(30)), (32768, 262144, 262144))
        owner = self.base_result()["participants"][0]
        six = self.raw(dict(self.base_result(), participants=roster(owner, 6)))
        seven = self.raw(dict(self.base_result(), participants=roster(owner, 7)))
        # Insignificant padding past each roster's budget is rejected, inside it accepted.
        with self.assertRaises(TransactionError): results_value(six + " " * MAX_RESULT_BYTES_LEGACY)
        results_value(seven + " " * MAX_RESULT_BYTES_LEGACY)
        with self.assertRaises(TransactionError): results_value(seven + " " * MAX_RESULT_BYTES)
        self.assertLess(MAX_RESULT_BYTES * 2, MAX_RESULT_REQUEST)

    def test_roster30_structural_maximum_fits_budget(self):
        # 30 rows, every row 30 targets with every scalar at its validator bound.
        rows = [dict(vehicle_id=vehicle_id(s), account_dbid=2**31 - 1 - s, name="Ё" * 24, team=1 + s % 2,
            type_compact_descr=2**31 - 1, health=10000, shots=192, direct_hits=192, piercings=192, damage_dealt=60000,
            damage_received=10000, kills=29, capture_points=600, dropped_capture_points=600, mileage_metres=200000,
            life_time=3600, killer_id=vehicle_id(29), death_reason=10, premature_leave=True) for s in range(30)]
        target = dict(spotted=1, death_reason=10, direct_hits=65535, explosion_hits=65535, piercings=65535, damage_dealt=65535,
            damage_assisted_track=65535, damage_assisted_radio=65535, crits=192, fire=10)
        details = dict(version=1, policy="test_lab.authoritative-interactions.v1",
            spotting_policy="test_lab.p08c.first-visible-enemy-lowest-slot.v1",
            rows=[dict(attacker_vehicle_id=vehicle_id(s), targets=[dict(target, vehicle_id=vehicle_id(t)) for t in range(30)]) for s in range(30)])
        value = dict(arena_id=2**63 - 1, arena_type_id=4, created_unix=2**32 - 1, winner_team=2, finish_reason=5,
            duration_seconds=3600, participants=rows, interaction_details=details)
        self.assertLessEqual(len(canonical(value)), MAX_RESULT_BYTES)
        six = dict(value, participants=rows[:6], interaction_details=dict(details, rows=[dict(r, targets=r["targets"][:6]) for r in details["rows"][:6]]))
        self.assertLessEqual(len(canonical(six)), MAX_RESULT_BYTES_LEGACY)


class Roster30TerminalTests(unittest.TestCase):
    setUp = terminal_tests.TerminalTests.setUp
    validate = terminal_tests.TerminalTests.validate
    bad = terminal_tests.TerminalTests.bad

    def test_roster30_terminal_roster_and_killer_slot(self):
        for n in (7, 30):
            self.assertEqual(self.validate(dict(self.value, roster_size=n))["roster_size"], n)
        self.bad(lambda: self.validate(dict(self.value, roster_size=31)))
        dead = dict(self.value, roster_size=30, crew_active=False, crew=[dict(c, alive=False) for c in self.value["crew"]],
            death=dict(reason=0, killer_slot=29, tick=1200))
        self.assertEqual(self.validate(dead)["death"]["killer_slot"], 29)
        self.bad(lambda: self.validate(dict(dead, death=dict(reason=0, killer_slot=30, tick=1200))))


class Roster30LossAndLateTests(unittest.TestCase):
    def test_roster30_loss_event_slots_shots_and_device_journal(self):
        good = dict(shot=MAX_BATTLE_SHOTS, attacker_slot=29, target_slot=0, tick=1200, device_sequence=MAX_DEVICE_SEQUENCE)
        _event(good); _event(dict(good, attacker_slot=6, target_slot=7, shot=961, device_sequence=15361))
        self.assertEqual((MAX_BATTLE_SHOTS, MAX_DEVICE_SEQUENCE), (4800, 76800))
        for change in (dict(attacker_slot=30), dict(target_slot=30), dict(target_slot=29), dict(shot=4801), dict(device_sequence=76801)):
            with self.assertRaises(TransactionError): _event(dict(good, **change))

    def test_roster30_late_seal_identity_and_budget(self):
        self.assertEqual([late.vehicle_id(s) for s in (0, 1, 2, 5, 6, 29)],
            [vehicle_id(s) for s in (0, 1, 2, 5, 6, 29)])
        with self.assertRaises(TransactionError): late.vehicle_id(30)
        self.assertEqual((late.seal_budget(6), late.seal_budget(7)), (32768, 393216))
        # A 30-actor tree (>4096 nodes) passes the seal decoder only.
        actor = dict(final_actor=dict(terminal_state=dict(devices=[dict(extra_index=26 + i, health=1, max_health=1) for i in range(40)],
            crew=[dict(crew_id="c%d" % i, alive=True) for i in range(6)])))
        raw = json.dumps(dict(results_json="x" * 200000, actors=[actor] * 30))
        late.decode(raw, late.MAX_SEAL_ROSTER30, late.SEAL_NODES)
        with self.assertRaises(TransactionError): late.decode(raw, late.MAX_SEAL_ROSTER30)


if __name__ == "__main__":
    unittest.main()
