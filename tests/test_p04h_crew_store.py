"""Real SQLite roster migrations, capacity, repeated seats and historical replay."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
import threading
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from tests import test_p04g_crew_store as previous
from p04d_crew_store import NativeCrewStore
from p04f_crew_store import NativeCrewTransferStore
from p04g_crew_store import NativeCrossVehicleCrewStore
from p09d_ammo_store import NativeAmmoStore
from p04h_crew_store import NativeRosterRecruitmentStore, COMMAND, RECRUIT_COMMAND, SOURCE_AUDIT_SHA256
from p04h_crew_projection import RosterRecruitmentProjectionSource, POLICY_SHA256, canonical, native_crew
from p04h_tankman_descriptor import decode_descriptor
from game_profile_tx import TransactionError


class RosterStoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        previous.CrossVehicleStoreTests.setUpClass.__func__(cls)
        cls.source = RosterRecruitmentProjectionSource(os.environ.get("P04H_TEST_BUNDLE") or os.environ["P04D_TEST_BUNDLE"])

    def setUp(self):
        previous.CrossVehicleStoreTests.setUp(self)
        previous.CrossVehicleStoreTests.activate(self)
        self.store.close()
        self.store = NativeRosterRecruitmentStore(self.database)

    profile = previous.CrossVehicleStoreTests.profile
    public = previous.CrossVehicleStoreTests.public
    request = previous.CrossVehicleStoreTests.request
    transfer = previous.CrossVehicleStoreTests.transfer
    ammo = previous.CrossVehicleStoreTests.ammo
    state = previous.CrossVehicleStoreTests.state
    reject = previous.CrossVehicleStoreTests.reject
    old_request = previous.CrossVehicleStoreTests.old_request
    reserve = previous.CrossVehicleStoreTests.reserve

    def activate(self):
        return self.store.migrate_roster(self.source, account_id=self.account, original_root=self.original)

    def hire(self, vehicle=1, slot=1, **changes):
        return self.store.recruit(self.request([3, vehicle, slot, 0], **changes), authenticated_account_id=self.account)

    def reopen(self):
        self.store.close()
        self.store = NativeRosterRecruitmentStore(self.database)
        self.store.initialize()

    def seven_hires(self):
        return [self.hire(vehicle, seat) for vehicle, seat in ((1,0),(1,1),(2,0),(2,1),(2,2),(2,3),(2,4))]

    def test_explicit_migration_preserves_all_old_state_and_grants_quota_once(self):
        self.reject("P04H_MIGRATION_REQUIRED", self.store.initialize)
        with NativeCrossVehicleCrewStore(self.database) as old: before = old.read_profile(self.account)
        result = self.activate(); after = self.profile()
        self.assertEqual((result["revision"], result["retained_tankmen"], result["new_tankmen"], result["free_recruitment_left"]), (10,3,0,13))
        for key in ("vehicles", "ammunition", "depot"): self.assertEqual(before[key], after[key])
        expected = deepcopy(before["crew_inventory"]); expected.update(policy_sha256=POLICY_SHA256, free_recruitment_left=13)
        self.assertEqual(after["crew_inventory"], expected)
        self.assertEqual(after["crew_roster_source_audit_sha256"], SOURCE_AUDIT_SHA256)
        self.assertEqual(self.public()["profile_version"], 9)
        self.assertEqual(self.public()["resources"], self.source.profile["resources"])
        self.assertEqual(self.store.ledger_count(self.account), 1)
        predecessor = json.loads(self.store.connection.execute("SELECT base_profile_json FROM p04h_crew_meta").fetchone()[0])
        self.assertEqual((predecessor["profile_version"], predecessor["crew_service"]["free_recruitment_left"]), (8,0))
        self.hire(); self.reopen(); before = self.state()
        self.assertEqual(self.activate()["status"], "already_migrated")
        self.assertEqual(self.state(), before)

    def test_migration_rollback_restores_both_check_tables_markers_and_old_writer(self):
        for point in ("after_roster_table_rebuild", "after_snapshot_update", "after_profile_projection", "before_roster_migration_commit"):
            self.store.failpoint = point
            self.reject("INJECTED_FAILURE", self.activate)
            with NativeCrossVehicleCrewStore(self.database) as old: self.assertEqual(old.read_profile(self.account)["revision"], 9)
        self.store.failpoint = None; self.activate()

    def test_wrong_source_bundle_or_G_audit_prevents_migration(self):
        original = self.source.bundle_sha256
        try:
            self.source.bundle_sha256 = "0" * 64
            self.reject("MIGRATION_SOURCE_CHANGED", self.activate)
        finally: self.source.bundle_sha256 = original
        self.store.connection.execute("UPDATE p04g_crew_meta SET source_audit_sha256=?", ("0"*64,)); self.store.connection.commit()
        self.reject("MIGRATION_SOURCE_CHANGED", self.activate)

    def test_every_old_writer_fails_closed_after_migration(self):
        self.activate(); before = self.state()
        for writer in (NativeCrewStore, NativeCrewTransferStore, NativeCrossVehicleCrewStore, NativeAmmoStore):
            with writer(self.database) as old:
                with self.assertRaises(TransactionError): old.read_profile(self.account)
                with self.assertRaises(TransactionError): old.service(self.request([3,1,6,2570,30,2826,10,3082,5,6,0,0,0,0,0,0]), authenticated_account_id=self.account)
        self.assertEqual(self.state(), before)

    def test_native_scenario_seven_roles_and_two_loader_reassignments(self):
        self.activate(); before = self.profile(); results = self.seven_hires()
        self.transfer([2,4,-1]); self.transfer([2,3,10]); self.transfer([2,4,9]); self.reopen()
        after = self.profile(); crew = after["crew_inventory"]
        self.assertEqual(native_crew(crew)[1], {1:[4,5], 2:[6,7,8,10,9]})
        self.assertEqual(crew["free_recruitment_left"], 6)
        self.assertEqual((after["revision"], crew["configuration_revision"]), (20,12))
        self.assertEqual([r["crew_assigned"] for r in self.public()["inventory"]], [True, True])
        self.assertEqual([r["role_level"] for r in self.public()["crew"]], [100]*3 + [50]*7)
        for old, new in zip(before["crew_inventory"]["members"], crew["members"]):
            for key in ("native_id", "crew_id", "role", "descriptor_hex"): self.assertEqual(old[key], new[key])
            self.assertEqual((new["vehicle_native_id"],new["seat"]), (-1,None))
        for row in crew["members"][3:]:
            decoded = decode_descriptor(bytes.fromhex(row["descriptor_hex"]))
            self.assertEqual(decoded["vehicle_type_id"], 13 if row["native_id"] in (4,5) else 28)
            self.assertEqual(row["crew_id"], self.account + ":recruit-crew:" + str(row["native_id"]))
        for result in results: self.assertEqual((result["status"], result["result_code"]), ("recruited",0))
        for key in ("vehicles", "ammunition", "depot"): self.assertEqual(before[key], after[key])
        self.assertEqual(self.public()["resources"], self.source.profile["resources"])

    def test_capacity_thirteen_successes_then_reject_without_identity_or_quota_recharge(self):
        self.activate()
        for number in range(4,17): self.hire(2, (number-4)%5)
        self.reopen(); self.assertEqual(len(self.profile()["crew_inventory"]["members"]), 16)
        self.assertEqual(self.profile()["crew_inventory"]["next_native_id"], 17)
        self.reject("FREE_RECRUITMENT_EXHAUSTED", self.hire)
        before = self.state(); self.activate(); self.assertEqual(before,self.state())
        self.reject("FREE_RECRUITMENT_EXHAUSTED", self.hire)

    def test_unknown_vehicle_role_slot_tariff_stale_foreign_and_boolean_reject(self):
        self.activate()
        for layout, code in (([3,3,0,0],"RECRUIT_SELECTION_UNSUPPORTED"),([3,1,2,0],"RECRUIT_SELECTION_UNSUPPORTED"),
            ([3,2,5,0],"RECRUIT_SELECTION_UNSUPPORTED"),([3,2,-1,0],"RECRUIT_SELECTION_UNSUPPORTED"),
            ([3,1,1,1],"RECRUIT_SELECTION_UNSUPPORTED"),([4,1,1,0],"SHOP_REVISION_MISMATCH"),([3,True,1,0],"INVALID_INPUT")):
            self.reject(code, lambda:self.store.recruit(self.request(layout), authenticated_account_id=self.account))
        self.reject("FOREIGN_ACCOUNT", lambda:self.store.recruit(self.request([3,1,1,0]), authenticated_account_id="other"))
        self.reject("FOREIGN_ACCOUNT", lambda:self.hire(native_database_id=999))
        self.reject("STALE_REVISION", lambda:self.hire(expected_revision=9))

    def test_recruit_rejects_reserved_target_and_transfer_rejects_reserved_source(self):
        self.activate(); self.hire(2,1); self.reserve(2)
        self.reject("VEHICLE_RESERVED",lambda:self.hire(2,3))
        self.reject("VEHICLE_RESERVED",lambda:self.transfer([2,1,-1]))
        self.hire(1,0)

    def test_noop_and_incompatible_roles_reject_and_loader_seats_can_replace_each_other(self):
        self.activate(); self.seven_hires()
        self.reject("NO_ASSIGNMENT_CHANGE", lambda:self.transfer([2,4,10]))
        self.reject("INCOMPATIBLE_CREW_ROLE", lambda:self.transfer([2,3,7]))
        self.transfer([2,3,10])
        self.assertEqual(native_crew(self.profile()["crew_inventory"])[1][2], [6,7,8,10,None])

    def test_shared_ammo_ledger_and_all_command_namespaces_are_atomic(self):
        self.activate(); self.ammo(); request = self.request([3,2,3,0]); self.store.recruit(request, authenticated_account_id=self.account)
        self.reject("DUPLICATE_PAYLOAD_MISMATCH", lambda:self.transfer([2,3,-1], command_key=request["command_key"]))
        self.reject("DUPLICATE_PAYLOAD_MISMATCH", lambda:self.ammo(command_key=request["command_key"]))
        crew = self.profile()["crew_inventory"]; self.ammo(command_key="later-ammo")
        self.assertEqual(self.profile()["crew_inventory"], crew)

    def test_D_and_G_replays_after_growth_reopen_preserve_original_bytes(self):
        request = dict(self.old_request(), expected_revision=9, command_key="G-cross", layout=[2,2,3])
        with NativeCrossVehicleCrewStore(self.database) as old: original = old.transfer(request,authenticated_account_id=self.account)
        self.activate(); self.seven_hires(); self.reopen(); before = self.state()
        self.assertEqual(self.store.transfer(request, authenticated_account_id=self.account), {**original,"replayed":True})
        legacy = self.store.recruit(self.old_request(), authenticated_account_id=self.account)
        self.assertEqual((legacy["revision"],legacy["replayed"]), (7,True))
        self.assertEqual(self.state(), before)

    def test_F_transfer_replay_after_H_growth_and_cross_assignment_is_frozen(self):
        # Create a fresh predecessor with a real F ledger before migrating G/H.
        case = previous.previous.TransferStoreTests("test_explicit_migration_required_and_preserves_two_tankmen")
        case.source, case.account, case.native_id, case.original = self.source, self.account, self.native_id, self.original
        self.addCleanup(case.doCleanups); case.setUp(); case.activate()
        request = case.request([1,1,-1], command_key="F-unload")
        original = case.store.transfer(request, authenticated_account_id=self.account); case.store.close()
        with NativeCrossVehicleCrewStore(case.database) as old: old.migrate_cross(self.source, account_id=self.account, original_root=self.original)
        with NativeRosterRecruitmentStore(case.database) as store:
            store.migrate_roster(self.source, account_id=self.account, original_root=self.original)
            hire = dict(request, command_key="H-hire", expected_revision=store.read_profile(self.account)["revision"], layout=[3,2,3,0])
            store.recruit(hire, authenticated_account_id=self.account)
            before = list(store.connection.iterdump())
            self.assertEqual(store.transfer(request, authenticated_account_id=self.account), {**original,"replayed":True})
            self.assertEqual(list(store.connection.iterdump()), before)

    def test_H_recruit_and_transfer_replays_use_immutable_before_after(self):
        self.activate(); request = self.request([3,2,3,0]); original = self.store.recruit(request, authenticated_account_id=self.account)
        move = self.request([2,4,4]); moved = self.store.transfer(move, authenticated_account_id=self.account)
        self.seven_hires(); self.reopen(); before = self.state()
        self.assertEqual(self.store.recruit(request,authenticated_account_id=self.account), {**original,"replayed":True})
        self.assertEqual(self.store.transfer(move,authenticated_account_id=self.account), {**moved,"replayed":True})
        self.assertEqual(self.state(),before)

    def test_rehashed_impossible_transition_and_changed_native_reply_fail_closed(self):
        self.activate(); request = self.request([3,2,3,0]); self.store.recruit(request, authenticated_account_id=self.account)
        c = self.store.connection
        result = json.loads(c.execute("SELECT result_json FROM game_command_ledger WHERE command_type=?",(RECRUIT_COMMAND,)).fetchone()[0])
        result["after_crew"]["members"][-1]["seat"] = 4; raw = canonical(result)
        c.execute("UPDATE game_command_ledger SET result_json=?,p09c_result_sha256=? WHERE command_type=?",(raw.decode(),hashlib.sha256(raw).hexdigest(),RECRUIT_COMMAND)); c.commit()
        self.reject("CORRUPT_STORE", lambda:self.store.recruit(request, authenticated_account_id=self.account))

    def test_all_shared_mutation_failpoints_roll_back_descriptor_allocator_quota_and_ammo(self):
        self.activate(); self.hire(2,3); before = self.state()
        for point in ("after_transfer_unassign","after_transfer_assign","after_transfer_meta_update","after_snapshot_update",
                      "after_profile_projection","after_transfer_ledger_insert","before_commit"):
            self.store.failpoint = point
            self.reject("INJECTED_FAILURE", lambda:self.hire(2,3))
            self.reopen(); self.assertEqual(self.state(), before)

    def test_unique_seat_and_sql_role_vehicle_checks(self):
        self.activate(); self.seven_hires(); c = self.store.connection
        for native,vehicle,seat in ((7,1,0),(9,2,1),(9,1,1),(9,2,None),(9,3,3),(9,2,4)):
            with self.assertRaises(sqlite3.IntegrityError):
                c.execute("UPDATE p04d_crew_member SET vehicle_native_id=?,seat=? WHERE native_id=?", (vehicle,seat,native))
            c.rollback()

    def test_concurrent_identical_recruit_commits_once_and_returns_durable_replay(self):
        self.activate(); request = self.request([3,2,3,0]); barrier = threading.Barrier(2)
        def run(_):
            with NativeRosterRecruitmentStore(self.database) as store:
                barrier.wait(); return store.recruit(request, authenticated_account_id=self.account)
        with ThreadPoolExecutor(max_workers=2) as pool: results = list(pool.map(run,range(2)))
        self.assertEqual(sorted(r["replayed"] for r in results), [False,True])
        self.assertEqual(results[0]["update_hex"],results[1]["update_hex"])
        self.assertEqual(len(self.profile()["crew_inventory"]["members"]),4)

    def test_full_fixture_exact_metadata14_and_complete_rosters(self):
        self.activate(); self.seven_hires()
        root = Path(self.temp.name)/"h-fixtures"
        if os.name == "nt": root = Path("\\\\?\\" + str(root.resolve()))
        published = self.store.publish(self.source,self.account,root)
        files = {p.name:p.read_bytes() for p in Path(published["fixture_dir"]).iterdir()}
        meta = json.loads(files["crew-roster.json"])
        self.assertEqual(set(meta), {"version","account_id","native_database_id","revision","wire_revision","policy_sha256","state_sha256",
            "command","transfer_command","role_level","vehicle_count","free_recruitment_left","configuration_revision","battle"})
        self.assertEqual((meta["command"],meta["transfer_command"],meta["role_level"],meta["free_recruitment_left"]),(309,105,50,6))
        self.assertEqual(meta["state_sha256"],hashlib.sha256(files["state.bin"]).hexdigest())
        self.assertFalse({"crew-service.json","crew-transfer.json","crew-cross-transfer.json"}.intersection(files))
        self.assertEqual(json.loads(files["manifest.json"])["profile_version"],9)
