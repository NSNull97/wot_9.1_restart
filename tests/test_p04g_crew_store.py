"""Real SQLite cross-vehicle migration, shared writes and historical replay."""
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
from tests import test_p04f_crew_store as previous
from p04f_crew_store import NativeCrewTransferStore
from p04d_crew_store import NativeCrewStore
from p09d_ammo_store import NativeAmmoStore
from p04g_crew_store import NativeCrossVehicleCrewStore, COMMAND, SOURCE_AUDIT_SHA256
from p04g_crew_projection import CrossVehicleCrewProjectionSource, POLICY_SHA256, canonical, native_crew
from game_profile_tx import TransactionError


class CrossVehicleStoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        previous.TransferStoreTests.setUpClass.__func__(cls)
        cls.source = CrossVehicleCrewProjectionSource(os.environ.get("P04G_TEST_BUNDLE")
            or os.environ.get("P04F_TEST_BUNDLE") or os.environ["P04D_TEST_BUNDLE"])

    def setUp(self):
        previous.TransferStoreTests.setUp(self)
        previous.TransferStoreTests.activate(self)
        self.store.close()
        self.store = NativeCrossVehicleCrewStore(self.database)

    profile = previous.TransferStoreTests.profile
    public = previous.TransferStoreTests.public
    request = previous.TransferStoreTests.request
    transfer = previous.TransferStoreTests.transfer
    recruit = previous.TransferStoreTests.recruit
    ammo = previous.TransferStoreTests.ammo
    state = previous.TransferStoreTests.state
    reject = previous.TransferStoreTests.reject
    old_request = previous.TransferStoreTests.old_request

    def activate(self):
        return self.store.migrate_cross(self.source, account_id=self.account, original_root=self.original)

    def reopen(self):
        self.store.close()
        self.store = NativeCrossVehicleCrewStore(self.database)
        self.store.initialize()

    def test_explicit_migration_retains_identity_quota_training_resources_ammo(self):
        self.reject("P04G_MIGRATION_REQUIRED", self.store.initialize)
        with NativeCrewTransferStore(self.database) as old:
            before = old.read_profile(self.account)
        result = self.activate()
        after = self.profile()
        self.assertEqual((result["revision"],result["retained_tankmen"],result["new_tankmen"]), (9,3,0))
        for field in ("ammunition","depot","vehicles"):
            self.assertEqual(before[field], after[field])
        expected = deepcopy(before["crew_inventory"]); expected["policy_sha256"] = POLICY_SHA256
        self.assertEqual(after["crew_inventory"], expected)
        self.assertEqual(after["crew_cross_source_audit_sha256"], SOURCE_AUDIT_SHA256)
        self.assertEqual(self.public()["profile_version"], 8)
        self.assertEqual(self.public()["resources"], self.source.profile["resources"])
        self.assertEqual([r["crew_assigned"] for r in self.public()["inventory"]], [True,False])
        self.assertEqual(self.store.ledger_count(self.account),1)

    def test_migration_rollback_restores_schema_index_rows_and_predecessor_writer(self):
        for point in ("after_cross_table_rebuild", "after_snapshot_update", "after_profile_projection", "before_cross_migration_commit"):
            self.store.failpoint=point
            self.reject("INJECTED_FAILURE", self.activate)
            with NativeCrewTransferStore(self.database) as old:
                self.assertEqual(old.read_profile(self.account)["revision"],8)
        self.store.failpoint=None
        self.assertEqual(self.activate()["status"],"migrated")

    def test_migration_rejects_changed_bundle_and_previous_audit(self):
        old=self.source.bundle_sha256
        try:
            self.source.bundle_sha256="0"*64
            self.reject("MIGRATION_SOURCE_CHANGED",self.activate)
        finally:self.source.bundle_sha256=old
        self.store.connection.execute("UPDATE p04f_crew_meta SET source_audit_sha256=?",("0"*64,))
        self.store.connection.commit()
        self.reject("MIGRATION_SOURCE_CHANGED",self.activate)

    def test_old_writers_fail_closed_after_new_migration(self):
        self.activate(); before=self.state()
        for writer in (NativeCrewStore,NativeCrewTransferStore,NativeAmmoStore):
            with writer(self.database) as old:
                with self.assertRaises(TransactionError):old.read_profile(self.account)
                with self.assertRaises(TransactionError):old.service(self.request([3,1,6,2570,30,2826,10,3082,5,6,0,0,0,0,0,0]),authenticated_account_id=self.account)
        self.assertEqual(self.state(),before)

    def test_direct_cross_vehicle_core_moves_source_and_replaces_target(self):
        self.activate(); before=self.profile(); identities=deepcopy(before["crew_inventory"]["members"])
        self.transfer([2,2,3])
        self.assertEqual(native_crew(self.profile()["crew_inventory"])[1],{1:[1,None],2:[None,None,3,None,None]})
        self.transfer([2,2,2]); self.transfer([2,0,1]); self.reopen()
        self.assertEqual(native_crew(self.profile()["crew_inventory"])[1],{1:[None,None],2:[1,None,2,None,None]})
        self.assertEqual([r["vehicle_native_id"] for r in self.profile()["crew_inventory"]["members"]],[2,2,-1])
        self.assertEqual([r["crew_assigned"] for r in self.public()["inventory"]],[False,False])
        for old,new in zip(identities,self.profile()["crew_inventory"]["members"]):
            for key in ("crew_id","native_id","descriptor_hex","role"):self.assertEqual(old[key],new[key])
        self.assertEqual(self.profile()["crew_inventory"]["configuration_revision"],5)
        self.assertEqual(self.profile()["ammunition"],before["ammunition"])

    def test_source_unload_barracks_target_and_return_use_same_atomic_writer(self):
        self.activate()
        for layout in ([1,1,-1],[2,2,3],[1,0,-1],[2,0,1],[2,2,-1],[1,1,3],[2,0,-1],[1,0,1]):
            before=self.profile(); reply=self.transfer(layout)
            self.assertEqual(reply["revision"],before["revision"]+1)
            self.assertEqual(self.profile()["crew_inventory"]["configuration_revision"],before["crew_inventory"]["configuration_revision"]+1)
        self.assertEqual(native_crew(self.profile()["crew_inventory"])[1],{1:[1,3],2:[None]*5})

    def test_whole_unload_only_affects_selected_vehicle_and_is_one_revision(self):
        self.activate(); self.transfer([2,2,3]); self.transfer([2,0,1]); self.transfer([1,1,2])
        before=self.profile(); self.transfer([2,-1,-1])
        self.assertEqual(native_crew(self.profile()["crew_inventory"])[1],{1:[None,2],2:[None]*5})
        self.assertEqual(self.profile()["revision"],before["revision"]+1)
        self.reject("NO_ASSIGNMENT_CHANGE",lambda:self.transfer([2,-1,-1]))

    def test_incompatible_roles_unknown_members_vehicles_and_slots_reject(self):
        self.activate()
        for layout,code in (([3,0,1],"UNKNOWN_VEHICLE"),([2,1,1],"INCOMPATIBLE_CREW_ROLE"),
            ([2,3,1],"INCOMPATIBLE_CREW_ROLE"),([2,4,2],"INCOMPATIBLE_CREW_ROLE"),([2,1,3],"INCOMPATIBLE_CREW_ROLE"),
            ([1,2,3],"TRANSFER_SELECTION_UNSUPPORTED"),([2,5,-1],"TRANSFER_SELECTION_UNSUPPORTED"),
            ([2,-1,1],"TRANSFER_SELECTION_UNSUPPORTED"),([2,2,99],"UNKNOWN_TANKMAN")):
            self.reject(code,lambda:self.transfer(layout))
        self.reject("FREE_RECRUITMENT_EXHAUSTED",self.recruit)

    def test_foreign_stale_boolean_and_duplicate_payload_reject_without_writes(self):
        self.activate(); request=self.request([2,2,3]); reply=self.store.transfer(request,authenticated_account_id=self.account)
        self.reject("FOREIGN_ACCOUNT",lambda:self.store.transfer(request,authenticated_account_id="other"))
        self.reject("FOREIGN_ACCOUNT",lambda:self.store.transfer({**request,"native_database_id":999},authenticated_account_id=self.account))
        self.reject("DUPLICATE_PAYLOAD_MISMATCH",lambda:self.store.transfer({**request,"wire_revision":9},authenticated_account_id=self.account))
        self.reject("STALE_REVISION",lambda:self.transfer([2,0,1],expected_revision=request["expected_revision"]))
        self.reject("INVALID_INPUT",lambda:self.transfer([True,2,3]))
        self.assertEqual(reply["status"],"transferred")

    def reserve(self,native):
        c=self.store.connection; old=c.execute("SELECT profile_json FROM game_profiles WHERE account_id=?",(self.account,)).fetchone()[0]
        vehicle=self.public()["inventory"][native-1]["inventory_id"]
        revision=self.profile()["revision"]
        c.execute("BEGIN IMMEDIATE")
        c.execute("UPDATE game_vehicle SET state='reserved',battle_id='synthetic-battle' WHERE account_id=? AND vehicle_id=?",(self.account,vehicle))
        self.store._save_crew_projection(self.account,revision+1,old);c.commit()

    def test_reserved_source_rejects_direct_cross_transfer(self):
        self.activate();self.reserve(1)
        self.reject("VEHICLE_RESERVED",lambda:self.transfer([2,2,3]))

    def test_reserved_target_rejects_barracks_equip_and_whole_unload(self):
        self.activate();self.reserve(2)
        self.reject("VEHICLE_RESERVED",lambda:self.transfer([2,2,2]))
        self.reject("VEHICLE_RESERVED",lambda:self.transfer([2,-1,-1]))

    def test_unrelated_reserved_vehicle_does_not_block_barracks_target(self):
        self.activate();self.reserve(1);self.transfer([2,2,2])
        self.assertEqual(native_crew(self.profile()["crew_inventory"])[1][2],[None,None,2,None,None])

    def test_shared_ammo_commands_preserve_both_partial_crews_and_namespace(self):
        self.activate();self.ammo();self.transfer([2,2,3]);crew=self.profile()["crew_inventory"]
        request=self.request([2,0,1]);self.store.transfer(request,authenticated_account_id=self.account)
        self.reject("DUPLICATE_PAYLOAD_MISMATCH",lambda:self.ammo(command_key=request["command_key"]))
        crew=self.profile()["crew_inventory"];self.ammo(command_key="second-ammo")
        self.assertEqual(self.profile()["crew_inventory"],crew)

    def test_legacy_F_transfer_replay_uses_immutable_F_state_after_cross_move(self):
        with NativeCrewTransferStore(self.database) as old:
            request=dict(self.old_request(),command_key="F-unload",expected_revision=8,layout=[1,1,-1])
            original=old.transfer(request,authenticated_account_id=self.account)
        self.activate();self.transfer([2,2,3]);self.reopen();before=self.state()
        self.assertEqual(self.store.transfer(request,authenticated_account_id=self.account),{**original,"replayed":True})
        self.assertEqual(self.state(),before)
        self.reject("DUPLICATE_PAYLOAD_MISMATCH",lambda:self.store.transfer({**request,"layout":[2,2,3]},authenticated_account_id=self.account))

    def test_legacy_D_recruit_replay_preserves_original_response_after_cross_move(self):
        self.activate();self.transfer([2,2,3]);self.transfer([2,0,1]);before=self.state()
        result=self.store.recruit(self.old_request(),authenticated_account_id=self.account)
        self.assertEqual((result["status"],result["revision"],result["replayed"]),("recruited",7,True))
        self.assertEqual(self.state(),before)

    def unrecruited_predecessor(self):
        case=previous.TransferStoreTests("test_explicit_migration_required_and_preserves_two_tankmen")
        case.source,case.account,case.native_id,case.original=self.source,self.account,self.native_id,self.original
        self.addCleanup(case.doCleanups)
        case.setUp();case.activate(False)
        return case

    def test_migration_rejects_unconsumed_quota_and_two_member_predecessor(self):
        case=self.unrecruited_predecessor()
        before=case.state();case.store.close()
        with NativeCrossVehicleCrewStore(case.database) as store:
            with self.assertRaises(TransactionError) as caught:
                store.migrate_cross(self.source,account_id=self.account,original_root=self.original)
            self.assertEqual(caught.exception.code,"P04G_REQUIRES_ACCEPTED_PROFILE7")
            self.assertEqual(list(store.connection.iterdump()),before)

    def test_legacy_F_recruit_replay_survives_cross_migration_and_reassignment(self):
        case=self.unrecruited_predecessor()
        request=case.request([3,1,1,0],command_key="F-recruit")
        original=case.store.recruit(request,authenticated_account_id=self.account)
        case.store.close()
        with NativeCrossVehicleCrewStore(case.database) as store:
            store.migrate_cross(self.source,account_id=self.account,original_root=self.original)
            transfer=dict(request,command_key="G-move",expected_revision=store.read_profile(self.account)["revision"],layout=[2,2,3])
            store.transfer(transfer,authenticated_account_id=self.account)
            before=list(store.connection.iterdump())
            self.assertEqual(store.recruit(request,authenticated_account_id=self.account),{**original,"replayed":True})
            self.assertEqual(list(store.connection.iterdump()),before)

    def test_current_replay_after_more_transfers_and_reopen_is_original_delta(self):
        self.activate();request=self.request([2,2,3]);original=self.store.transfer(request,authenticated_account_id=self.account)
        self.transfer([1,1,3]);self.transfer([2,0,1]);self.reopen();before=self.state()
        self.assertEqual(self.store.transfer(request,authenticated_account_id=self.account),{**original,"replayed":True})
        self.assertEqual(self.state(),before)

    def test_rehashed_impossible_cross_transition_rejected(self):
        self.activate();request=self.request([2,2,3]);self.store.transfer(request,authenticated_account_id=self.account)
        c=self.store.connection;result=json.loads(c.execute("SELECT result_json FROM game_command_ledger WHERE command_type=?",(COMMAND,)).fetchone()[0])
        result["after_crew"]["members"][2].update(vehicle_native_id=1,seat=1);raw=canonical(result)
        c.execute("UPDATE game_command_ledger SET result_json=?,p09c_result_sha256=? WHERE command_type=?",(raw.decode(),hashlib.sha256(raw).hexdigest(),COMMAND));c.commit()
        self.reject("CORRUPT_STORE",lambda:self.store.transfer(request,authenticated_account_id=self.account))

    def test_every_mutation_failpoint_restores_both_vehicles_and_ledger(self):
        self.activate();self.transfer([2,2,2]);before=self.state()
        for point in ("after_transfer_unassign","after_transfer_assign","after_transfer_meta_update",
            "after_snapshot_update","after_profile_projection","after_transfer_ledger_insert","before_commit"):
            self.store.failpoint=point
            self.reject("INJECTED_FAILURE",lambda:self.transfer([2,2,3]))
            self.reopen();self.assertEqual(self.state(),before)

    def test_unique_and_role_seat_checks_reject_direct_invalid_rows(self):
        self.activate();c=self.store.connection
        for vehicle,seat in ((2,1),(2,3),(2,None),(1,0),(3,2)):
            with self.assertRaises(sqlite3.IntegrityError):
                c.execute("UPDATE p04d_crew_member SET vehicle_native_id=?,seat=? WHERE native_id=3",(vehicle,seat))
            c.rollback()
        self.transfer([2,2,3])
        with self.assertRaises(sqlite3.IntegrityError):
            c.execute("UPDATE p04d_crew_member SET vehicle_native_id=2,seat=2 WHERE native_id=2")
        c.rollback()

    def test_migration_repetition_after_transfers_never_restores_assignments(self):
        self.activate();self.transfer([2,2,3]);self.reopen();before=self.state()
        self.assertEqual(self.activate()["status"],"already_migrated")
        self.assertEqual(self.state(),before)

    def test_fixture_exact_G_metadata_and_both_vehicle_state(self):
        self.activate();self.transfer([2,2,3]);root=Path(self.temp.name)/"g-fixtures"
        if os.name=="nt":root=Path("\\\\?\\"+str(root.resolve()))
        published=self.store.publish(self.source,self.account,root);files={p.name:p.read_bytes() for p in Path(published["fixture_dir"]).iterdir()}
        self.assertNotIn("crew-transfer.json",files);self.assertNotIn("crew-service.json",files)
        metadata=json.loads(files["crew-cross-transfer.json"])
        self.assertEqual(set(metadata),{"version","account_id","native_database_id","revision","wire_revision","policy_sha256","state_sha256","command","vehicle_count","free_recruitment_left","configuration_revision","battle"})
        self.assertEqual((metadata["vehicle_count"],metadata["policy_sha256"],metadata["battle"]),(2,POLICY_SHA256,False))
        self.assertEqual(metadata["state_sha256"],hashlib.sha256(files["state.bin"]).hexdigest())
        self.assertEqual(json.loads(files["manifest.json"])["profile_version"],8)
        state=self.source.state(self.profile(),self.store.layouts(self.account))
        self.assertEqual(state["inventory"][1]["crew"],{1:[1,None],2:[None,None,3,None,None]})

    def test_concurrent_cross_assignment_commits_once(self):
        self.activate();request=self.request([2,2,3]);barrier=threading.Barrier(2)
        def run(_):
            with NativeCrossVehicleCrewStore(self.database) as store:
                barrier.wait();return store.transfer(request,authenticated_account_id=self.account)
        with ThreadPoolExecutor(2) as pool:results=list(pool.map(run,range(2)))
        self.assertEqual(sorted(r["replayed"] for r in results),[False,True])
        self.assertEqual(self.profile()["revision"],10)

    def test_concurrent_distinct_assignments_have_only_one_revision_winner(self):
        self.activate();requests=[self.request([2,2,3]),self.request([2,0,1],command_key="other-cross")];barrier=threading.Barrier(2)
        def run(index):
            with NativeCrossVehicleCrewStore(self.database) as store:
                barrier.wait()
                try:return store.transfer(requests[index],authenticated_account_id=self.account)["status"]
                except TransactionError as error:return error.code
        with ThreadPoolExecutor(2) as pool:results=list(pool.map(run,range(2)))
        self.assertEqual(sorted(results),["STALE_REVISION","transferred"])
        self.assertEqual(self.profile()["revision"],10)
