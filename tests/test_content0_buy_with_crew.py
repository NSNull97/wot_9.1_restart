"""CONTENT-0: original VehicleBuyWindow purchase with crew (tariff 0/1/2) and base ammunition.

Pure checks (command options, default-ammo algorithm/table, update chaining) always run.
The store cases run the retained P04M fixture chain in catalog mode with crew contract v2
(real isolated SQLite); without the P04D..P09D test bundles they are skipped (NOT_RUN).
"""
from collections import deque
import struct
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "tools"))
from game_profile_tx import TransactionError
from p09e_native_commands import NativeRequest, validate_selection, domain_request, CREW_TARIFF_LEVELS
from p09e_research_projection import chained_updates
from p09e_research_service import native_service
import content0_default_ammo as ammo

SHOP = 5


def unpickle(raw):
    """Bounded decoder of the protocol-2 primitive subset p09d encode() emits (test only)."""
    assert raw[:2] == b"\x80\x02" and raw[-1:] == b"." and len(raw) <= 240, raw
    stack, marks, i = [], [], 2
    while True:
        op = raw[i:i + 1]; i += 1
        if op == b".": break
        if op == b"}": stack.append({})
        elif op == b"]": stack.append([])
        elif op == b")": stack.append(())
        elif op == b"(": marks.append(len(stack))
        elif op == b"N": stack.append(None)
        elif op in (b"\x88", b"\x89"): stack.append(op == b"\x88")
        elif op == b"K": stack.append(raw[i]); i += 1
        elif op == b"M": stack.append(struct.unpack_from("<H", raw, i)[0]); i += 2
        elif op == b"J": stack.append(struct.unpack_from("<i", raw, i)[0]); i += 4
        elif op == b"U": n = raw[i]; stack.append(raw[i + 1:i + 1 + n]); i += 1 + n
        elif op in (b"u", b"e", b"t"):
            start = marks.pop(); items = stack[start:]; del stack[start:]
            if op == b"t": stack.append(tuple(items))
            elif op == b"e": stack[-1].extend(items)
            else: stack[-1].update(zip(items[::2], items[1::2]))
        else: raise AssertionError("unexpected opcode %r" % op)
    assert len(stack) == 1 and not marks
    return stack[0]


def text_keys(value):
    """bytes dict keys of the pickle subset -> str, recursively (U opcodes carry both)."""
    if type(value) is dict:
        return {(k.decode() if type(k) is bytes else k): text_keys(v) for k, v in value.items()}
    if type(value) is list: return [text_keys(v) for v in value]
    return value


class OptionTests(unittest.TestCase):
    def check(self, flags, tariff):
        validate_selection(NativeRequest(1, 301, (SHOP, 3329, flags, tariff)), shop_revision=SHOP)

    def test_window_choices_are_admitted_and_everything_else_is_unavailable(self):
        for flags in (0, 16): self.check(flags, -1)
        for flags in (1, 17):
            for tariff in (0, 1, 2): self.check(flags, tariff)
        for flags, tariff in ((0, 0), (16, 2), (1, -1), (17, 3), (1, 5), (2, -1), (32, -1), (18, 0), (-1, -1), (0, -2)):
            with self.assertRaises(TransactionError) as caught: self.check(flags, tariff)
            self.assertEqual(caught.exception.code, "AUTOBUY_CREW_SHELLS_UNSUPPORTED", (flags, tariff))
        self.assertEqual(CREW_TARIFF_LEVELS, {0: 50, 1: 75, 2: 100})

    def test_domain_request_maps_flags_to_one_equipped_operation(self):
        class Catalog:
            vehicles = {"vehicle:ussr:MS-1": {"native_compact_id": 3329}}
            modules = {}
        aggregate = {"research": {"vehicles": []}}
        def domain(flags, tariff):
            return domain_request(NativeRequest(1, 301, (SHOP, 3329, flags, tariff)), catalog=Catalog, aggregate=aggregate,
                                  account_id="a", command_key="k", expected_revision=9, shop_revision=SHOP)
        self.assertEqual((domain(0, -1)["operation"], domain(0, -1)["payload"]), ("buy_vehicle", {"vehicle_id": "vehicle:ussr:MS-1"}))
        self.assertEqual(domain(16, -1)["payload"], {"vehicle_id": "vehicle:ussr:MS-1", "crew_role_level": 0, "load_shells": True})
        self.assertEqual(domain(1, 0)["payload"], {"vehicle_id": "vehicle:ussr:MS-1", "crew_role_level": 50, "load_shells": False})
        self.assertEqual(domain(17, 2)["payload"], {"vehicle_id": "vehicle:ussr:MS-1", "crew_role_level": 100, "load_shells": True})
        self.assertEqual(domain(1, 1)["operation"], "buy_vehicle_equipped")


class DefaultAmmoTests(unittest.TestCase):
    def test_algorithm_matches_getAmmoForGun(self):
        self.assertEqual(ammo.default_counts(30, 1, [0.6, 0.0, 0.4]), [18, 0, 12])
        # Clip rounding: int(portion * max / clip + 0.5) * clip, capped at maxAmmo in shot order.
        self.assertEqual(ammo.default_counts(100, 6, [0.5, 0.5]), [48, 48])
        self.assertEqual(ammo.default_counts(10, 4, [0.7, 0.7]), [8, 2])
        self.assertEqual(ammo.default_counts(96, 1, [1.0, 0.0, 0.0]), [96, 0, 0])
        with self.assertRaises(ammo.DefaultAmmoError): ammo.default_counts(10, 1, [1.5])

    def test_committed_table_is_canonical_and_covers_the_test_lab_catalogue(self):
        import json
        document = ammo.table()
        catalog = json.loads((ROOT / "config/test_lab/catalog.v1.json").read_bytes())["vehicles"]
        self.assertEqual(set(document["vehicles"]), {v["kind"] for v in catalog})
        for v in catalog:
            capacity, counts = ammo.default_ammo(v["kind"])
            self.assertEqual(capacity, v["ammo_capacity"])
            self.assertEqual(set(counts), {s["native_compact_id"] for s in v["shells"]})
            self.assertLessEqual(sum(counts.values()), capacity)
        self.assertEqual(ammo.default_ammo("ms1"), (96, {2570: 96, 2826: 0, 3082: 0}))
        self.assertEqual(ammo.default_ammo("is7"), (30, {14602: 18, 14858: 0, 15114: 12}))
        self.assertIsNone(ammo.default_ammo("unknown-kind"))


class ChainTests(unittest.TestCase):
    def test_parts_pack_into_consecutive_bounded_diffs(self):
        first = {"prevRev": 7, "rev": 8, "inventory": {1: {"compDescr": {9: b"x" * 40}}}}
        parts = [{"inventory": {8: {"compDescr": {n: bytes(25)}, "vehicle": {n: 9}}, 1: {"crew": {9: list(range(n))}}},
                  "stats": {"freeTMenLeft": 100 - n}} for n in range(1, 7)]
        updates = chained_updates(first, parts, 7, 12)
        self.assertGreater(len(updates), 1)
        trees = [unpickle(u) for u in updates]
        self.assertEqual([(t[b"prevRev"], t[b"rev"]) for t in trees], [(7 + i, 8 + i) for i in range(len(updates))])
        members = {k for t in trees for k in t.get(b"inventory", {}).get(8, {}).get(b"compDescr", {})}
        self.assertEqual(members, set(range(1, 7)))
        self.assertEqual(trees[-1][b"stats"][b"freeTMenLeft"], 94)
        self.assertEqual(trees[-1][b"inventory"][1][b"crew"][9], list(range(6)))
        self.assertTrue(all(len(u) <= 240 for u in updates))
        with self.assertRaises(TransactionError): chained_updates(first, parts, 7, 1)
        with self.assertRaises(TransactionError): chained_updates(first, [{"x": b"y" * 300}], 7, 12)


try:
    # Module import: a class imported by name would also be collected and run here.
    from tests import test_p04m_pool_crew_v2 as crew_v2
    CrewV2Tests = crew_v2.CrewV2Tests
    from p04m_pool_crew import decode
    from p09e_research_store import ECONOMY_POLICY
    import catalog_v1
except Exception as error:  # the retained fixture chain is optional in a bare checkout
    CrewV2Tests, IMPORT_ERROR = None, error
else:
    IMPORT_ERROR = None


@unittest.skipIf(CrewV2Tests is None, "NOT_RUN: retained P04M fixture chain unavailable: %s" % IMPORT_ERROR)
class BuyWithCrewStoreTests(CrewV2Tests if CrewV2Tests is not None else unittest.TestCase):
    CATALOG = True

    def setUp(self):
        crew_v2.CrewV2Tests.setUp(self)
        self.migrate(2)
        # The fixture account has the historical slot count; the stand grant gives room for the purchases.
        self.store.apply_test_lab_economy(account_id=self.account, garage_slots=12, policy=ECONOMY_POLICY)
        self.wire = 1

    def test_content0_stand_grant_adds_a_vehicle_the_shop_never_sells(self):
        # Owner 12.11: secret / not-in-shop vehicles cannot be bought; the stand grants them.
        from p09e_research_store import TransactionError
        catalog = self.store.catalog
        hidden = sorted(v for v, row in catalog.vehicles.items()
                        if not row.get("acquisition_allowed") and not row.get("unsupported_reason")
                        and not set(row.get("tags", ())) & {"observer", "event_battles"}
                        and v in self.store.registry.by_vehicle)
        self.assertTrue(hidden, "the fixture catalogue has a hidden vehicle with a battle profile")
        target = hidden[0]
        before = self.store.read_profile(self.account)
        request = {"account_id": self.account, "command_key": "client-grant", "expected_revision": before["revision"],
                   "operation": "grant_vehicle", "payload": {"vehicle_id": target}}
        with self.assertRaises(TransactionError):
            self.store.execute(request, authenticated_account_id=self.account)   # no client path to the grant
        with self.assertRaises(TransactionError):
            self.store.execute(dict(request, command_key="client-buy", operation="buy_vehicle"), authenticated_account_id=self.account)
        observer = [v for v, row in catalog.vehicles.items() if "observer" in row.get("tags", ())]
        for vehicle_id in observer[:1]:
            with self.assertRaises(TransactionError):
                self.store.grant_vehicle(account_id=self.account, vehicle_id=vehicle_id)
        self.assertEqual(self.store.read_profile(self.account), before, "refusals write nothing")
        result = self.store.grant_vehicle(account_id=self.account, vehicle_id=target)
        after = self.store.read_profile(self.account)
        self.assertEqual((result["status"], after["revision"]), ("applied", before["revision"] + 1))
        self.assertEqual(result["details"]["stand_grant"], True)
        self.assertIn(target, [r["vehicle_id"] for r in after["research"]["vehicles"]])
        self.assertIn(target, after["research"]["unlocked"])
        self.assertEqual(self.store.grant_vehicle(account_id=self.account, vehicle_id=target)["status"], "owned")
        self.assertEqual(self.store.read_profile(self.account), after)

    def test_content0_economy_topup_raises_an_old_account_to_the_current_floor(self):
        # Owner 12.11 (stand -21): accounts granted before the floor rose kept 100 rounds of an 1800-round belt.
        self.assertEqual(self.store.economy_topup(account_id=self.account)["status"], "unchanged")
        before = self.store.read_profile(self.account)
        key = self.store.depot_keys[0]
        target = before["depot"][key] + 777
        self.store.depot_mount_capacity[key] = target    # as if a larger magazine now carried this shell
        result = self.store.economy_topup(account_id=self.account)
        after = self.store.read_profile(self.account)
        self.assertEqual((result["status"], result["revision"]), ("topped_up", before["revision"] + 1))
        self.assertEqual(result["raised"], {key: [before["depot"][key], target]})
        self.assertEqual(after["depot"][key], target)
        self.assertEqual({k: v for k, v in after["depot"].items() if k != key},
                         {k: v for k, v in before["depot"].items() if k != key})
        self.assertEqual(self.store.economy_topup(account_id=self.account)["status"], "unchanged")

    def research_to(self, target):
        known = set(self.profile()["research"]["unlocked"])
        if target in known: return
        paths = deque([(vehicle, []) for vehicle in sorted(known) if vehicle.startswith("vehicle:")]); seen = set(known)
        path = None
        while paths:
            vehicle, edges = paths.popleft()
            if vehicle == target: path = edges; break
            for edge in self.catalog.unlocks:
                if edge["vehicle_id"] == vehicle and edge["item_id"].startswith("vehicle:") and edge["item_id"] not in seen:
                    seen.add(edge["item_id"]); paths.append((edge["item_id"], edges + [edge]))
        self.assertIsNotNone(path)
        def unlock(edge, stack=()):
            known = set(self.profile()["research"]["unlocked"])
            if edge["item_id"] in known: return
            for item in edge["prerequisite_ids"]:
                if item not in set(self.profile()["research"]["unlocked"]):
                    choices = [r for r in self.catalog.unlocks if r["item_id"] == item and r["vehicle_id"] in known]
                    choices.sort(key=lambda r: r["vehicle_id"] != edge["vehicle_id"])
                    self.assertTrue(choices); unlock(choices[0], stack + (edge["item_id"],))
            self.act("research", {"vehicle_id": edge["vehicle_id"], "unlock_index": edge["native_index"]})
        for edge in path: unlock(edge)

    def native_request(self, vehicle, flags, tariff, key=None):
        self.serial += 1
        return dict(account_id=self.account, native_database_id=self.native_id, command_key=key or "buy-crew:" + str(self.serial),
                    expected_revision=self.profile()["revision"], wire_revision=self.wire, command=301,
                    arguments=[SHOP, self.catalog.vehicles[vehicle]["native_compact_id"], flags, tariff])

    def buy(self, vehicle, flags, tariff):
        self.research_to(vehicle)
        request = self.native_request(vehicle, flags, tariff)
        return request, native_service(self.store, request, authenticated_account_id=self.account)

    def owned(self, vehicle):
        return next(r for r in self.profile()["research"]["vehicles"] if r["vehicle_id"] == vehicle)

    def updates(self, response):
        return [bytes.fromhex(response["update_hex"])] + [bytes.fromhex(h) for h in response.get("extra_update_hex", [])]

    def assert_crew(self, vehicle, level):
        owned = self.owned(vehicle); crew = self.profile()["crew_inventory"]
        roles = [seat["roles"][0] for seat in catalog_v1.by_kind(self.store.registry.by_vehicle[vehicle].kind)["crew"]]
        rows = sorted((r for r in crew["members"] if r["vehicle_native_id"] == owned["native_id"]), key=lambda r: r["seat"])
        self.assertEqual([r["seat"] for r in rows], list(range(len(roles))))
        self.assertEqual([r["role"] for r in rows], roles)
        for row in rows:
            decoded = decode(bytes.fromhex(row["descriptor_hex"]))
            self.assertEqual((decoded["role_level"], decoded["role"], decoded["skills"]), (level, row["role"], []))
        public = self.public()
        entry = next(e for e in public["inventory"] if e["inventory_id"] == owned["vehicle_inventory_id"])
        self.assertTrue(entry["crew_assigned"])
        return rows

    def test_each_tariff_hires_the_full_crew_at_its_level_in_one_transaction(self):
        for vehicle, tariff, level in (("vehicle:ussr:T-26", 0, 50), ("vehicle:ussr:BT-2", 1, 75), ("vehicle:ussr:KV-3", 2, 100)):
            before = self.profile()
            request, response = self.buy(vehicle, 1, tariff)
            self.assertEqual((response["status"], response["result_code"], response["replayed"]), ("researched", 0, False))
            after = self.profile()
            rows = self.assert_crew(vehicle, level)
            self.assertEqual(after["revision"], request["expected_revision"] + 1)
            self.assertEqual(after["crew_inventory"]["next_native_id"], before["crew_inventory"]["next_native_id"] + len(rows))
            self.assertEqual(after["depot"], before["depot"])
            updates = self.updates(response)
            self.assertEqual(response["wire_revision"], self.wire + len(updates))
            trees = [unpickle(u) for u in updates]
            self.assertEqual([(t[b"prevRev"], t[b"rev"]) for t in trees], [(self.wire + i, self.wire + i + 1) for i in range(len(trees))])
            native = self.owned(vehicle)["native_id"]
            self.assertIn(native, trees[0][b"inventory"][1][b"compDescr"])
            sent = {k: v for t in trees for k, v in t.get(b"inventory", {}).get(8, {}).get(b"compDescr", {}).items()}
            self.assertEqual(sent, {r["native_id"]: bytes.fromhex(r["descriptor_hex"]) for r in rows})
            last_crew = [t[b"inventory"][1][b"crew"][native] for t in trees if b"crew" in t.get(b"inventory", {}).get(1, {})][-1]
            self.assertEqual(last_crew, [r["native_id"] for r in rows])
            self.assertEqual([t for t in trees if b"stats" in t][-1][b"stats"][b"freeTMenLeft"], after["crew_inventory"]["free_recruitment_left"])
            self.wire = response["wire_revision"]
            # Replay of the same command is the same answer, no second write.
            self.assertEqual(native_service(self.store, request, authenticated_account_id=self.account), {**response, "replayed": True})
            self.assertEqual(self.profile(), after)
        # KV-3's six tankmen do not fit one 240-byte diff.
        self.assertGreater(len(self.updates(response)), 1)

    def test_base_ammunition_is_bought_free_and_loaded_with_crew_or_alone(self):
        for vehicle, flags in (("vehicle:ussr:T-26", 17), ("vehicle:ussr:BT-2", 16)):
            before = self.profile()
            request, response = self.buy(vehicle, flags, 1 if flags & 1 else -1)
            self.assertEqual(response["status"], "researched")
            p = self.store.registry.by_vehicle[vehicle]
            capacity, counts = ammo.default_ammo(p.kind)
            owned = self.owned(vehicle); after = self.profile()
            loaded = next(r for r in after["ammunition"] if r["vehicle_id"] == owned["vehicle_inventory_id"])["loaded"]
            self.assertEqual({self.store.shells[k].native_compact_id: n for k, n in loaded.items()}, counts)
            self.assertEqual(after["depot"], before["depot"])  # bought free, the shared depot is not drawn
            layout = self.store.layouts(self.account)[owned["native_id"]]
            self.assertEqual(dict(zip(layout[::2], layout[1::2])), counts)
            trees = [unpickle(u) for u in self.updates(response)]
            shells = [t[b"inventory"][1][b"shells"][owned["native_id"]] for t in trees if b"shells" in t.get(b"inventory", {}).get(1, {})]
            self.assertEqual(dict(zip(shells[-1][::2], shells[-1][1::2])), counts)
            crew = [r for r in after["crew_inventory"]["members"] if r["vehicle_native_id"] == owned["native_id"]]
            self.assertEqual(bool(crew), bool(flags & 1))
            public = next(e for e in self.public()["inventory"] if e["inventory_id"] == owned["vehicle_inventory_id"])
            self.assertEqual(public["ammunition_count"], sum(counts.values()))
            self.wire = response["wire_revision"]

    def assert_refused(self, request, code=None):
        before = self.state()
        response = native_service(self.store, request, authenticated_account_id=self.account)
        self.assertEqual((response["status"], response["result_code"], response["update_hex"]), ("rejected", -10, ""))
        self.assertEqual(response["wire_revision"], request["wire_revision"])
        self.assertEqual(self.state(), before)
        self.assertFalse(self.store.connection.in_transaction)

    def test_unsupported_options_refuse_without_a_write(self):
        self.research_to("vehicle:ussr:KV-3")
        for flags, tariff in ((1, -1), (1, 3), (2, -1), (16, 0)):
            self.assert_refused(self.native_request("vehicle:ussr:KV-3", flags, tariff))
        request, response = self.buy("vehicle:ussr:KV-3", 0, -1)  # the plain purchase is unchanged
        self.assertEqual(response["status"], "researched")
        self.assertEqual(response["wire_revision"], self.wire + 1)
        self.assertNotIn("extra_update_hex", response)
        owned = self.owned("vehicle:ussr:KV-3")
        self.assertFalse(any(r["vehicle_native_id"] == owned["native_id"] for r in self.profile()["crew_inventory"]["members"]))

    def test_exhausted_lifetime_allocator_refuses_the_whole_purchase(self):
        # Crew contract v1 has 16 lifetime identities: barracks hires leave fewer than KV-3's six seats.
        self.migrate(1)
        while self.profile()["crew_inventory"]["free_recruitment_left"] >= 6:
            self.free_hire()
        self.research_to("vehicle:ussr:KV-3")
        request = self.native_request("vehicle:ussr:KV-3", 17, 0)
        self.assert_refused(request)
        domain = domain_request(NativeRequest(1, 301, tuple(request["arguments"])), catalog=self.store.catalog,
            aggregate=self.profile(), account_id=self.account, command_key=request["command_key"],
            expected_revision=request["expected_revision"], shop_revision=SHOP)
        with self.assertRaises(TransactionError) as caught:
            self.store.execute(domain, authenticated_account_id=self.account)
        self.assertEqual(caught.exception.code, "FREE_RECRUITMENT_EXHAUSTED")
        self.assertFalse(any(r["vehicle_id"] == "vehicle:ussr:KV-3" for r in self.profile()["research"]["vehicles"]))

    def test_failpoints_leave_no_vehicle_crew_or_ammunition(self):
        self.research_to("vehicle:ussr:T-26")
        for point in ("after_research_vehicle_insert", "after_research_state", "after_purchase_crew", "after_purchase_equipment",
                      "after_snapshot_update", "after_profile_projection", "after_research_ledger", "before_commit"):
            before = self.state()
            request = self.native_request("vehicle:ussr:T-26", 17, 2)
            self.store.failpoint = point
            try:
                with self.assertRaises(TransactionError) as caught:
                    native_service(self.store, request, authenticated_account_id=self.account)
                self.assertEqual(caught.exception.code, "INJECTED_FAILURE", point)
            finally:
                self.store.failpoint = None
            self.assertEqual(self.state(), before, point)
            self.assertFalse(self.store.connection.in_transaction)
        request, response = self.buy("vehicle:ussr:T-26", 17, 2)
        self.assertEqual(response["status"], "researched")
        self.assert_crew("vehicle:ussr:T-26", 100)

    def test_v1_crew_contract_refuses_school_and_academy(self):
        self.migrate(1)
        self.research_to("vehicle:ussr:T-26")
        for tariff in (1, 2):
            self.assert_refused(self.native_request("vehicle:ussr:T-26", 1, tariff))
        request, response = self.buy("vehicle:ussr:T-26", 1, 0)
        self.assertEqual(response["status"], "researched")
        self.assert_crew("vehicle:ussr:T-26", 50)


if CrewV2Tests is not None:
    # Only the cases above belong to this module; the inherited v2 cases run in their own.
    for _name in [n for n in dir(CrewV2Tests) if n.startswith("test_")]:
        if getattr(BuyWithCrewStoreTests, _name) is getattr(CrewV2Tests, _name):
            setattr(BuyWithCrewStoreTests, _name, None)
    del _name
    CrewV2Tests = None  # not a module-level TestCase of this file


if __name__ == "__main__":
    unittest.main()
