"""Create a NEW private accepted-profile fixture and exercise real P09E SQLite.

No credentials, native process, shared DB or installation is used. This is an
automatic service harness, never evidence that original Flash callbacks ran.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from p04d_crew_store import NativeCrewStore
from p04f_crew_store import NativeCrewTransferStore
from p04g_crew_store import NativeCrossVehicleCrewStore
from p04h_crew_store import NativeRosterRecruitmentStore
from p04i_crew_store import NativeCrewProgressionStore
from p04j_crew_store import NativeCrewDismissalStore
from p04k_crew_store import NativeBarracksRecruitmentStore
from p09e_research_catalog import load_catalog
from p09e_research_projection import ResearchProjectionSource, SHOP_REVISION
from p09e_research_store import ResearchStore, POLICY
from p09e_research_service import native_service
from p09d_ammo_projection import canonical
from destructible_catalog import no_links


def seed(directory, bundle, original):
    catalog = load_catalog(original)
    source = ResearchProjectionSource(bundle, catalog)
    account = source.profile["account_id"]
    database = directory / "game.sqlite"
    if database.exists(): raise ValueError("new isolated database required")
    with sqlite3.connect(database) as db:
        db.executescript("""PRAGMA user_version=1;
            CREATE TABLE game_meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
            CREATE TABLE game_profiles(native_id INTEGER PRIMARY KEY AUTOINCREMENT,account_id TEXT NOT NULL UNIQUE,profile_json TEXT NOT NULL);
            CREATE TABLE game_limits(key_hash TEXT PRIMARY KEY,hits INTEGER NOT NULL,resets_at INTEGER NOT NULL);""")
        db.execute("INSERT INTO game_profiles VALUES (?,?,?)", (source.profile["native_database_id"], account, canonical(source.profile).decode("ascii")))
    with NativeCrewStore(database) as store:
        store.migrate(source, account_id=account, original_root=original, grant={"grant_id": "p09d-test-depot-v1", "quantity_each": 100})
        store.migrate_crew(source, account_id=account, original_root=original)
        store.recruit(dict(account_id=account, native_database_id=source.profile["native_database_id"],
            command_key="harness:old-recruit", expected_revision=6, wire_revision=1, layout=[3, 1, 1, 0]), authenticated_account_id=account)
    with NativeCrewTransferStore(database) as store: store.migrate_transfer(source, account_id=account, original_root=original)
    with NativeCrossVehicleCrewStore(database) as store: store.migrate_cross(source, account_id=account, original_root=original)
    # The accepted P04H-P04K chain ends at profile12, the only research predecessor.
    with NativeRosterRecruitmentStore(database) as store: store.migrate_roster(source, account_id=account, original_root=original)
    with NativeCrewProgressionStore(database) as store: store.migrate_progression(source, account_id=account, original_root=original)
    with NativeCrewDismissalStore(database) as store: store.migrate_dismissal(source, account_id=account, original_root=original)
    with NativeBarracksRecruitmentStore(database) as store: store.migrate_barracks(source, account_id=account, original_root=original)
    return database, source, catalog


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--bundle", required=True); p.add_argument("--original", required=True); p.add_argument("--out", required=True)
    p.add_argument("--seed-only", action="store_true")
    args = p.parse_args()
    directory = no_links(args.out).resolve()
    allowed = Path(__file__).resolve().parents[1] / "local"
    if not directory.is_relative_to(allowed.resolve()): raise ValueError("isolated output must remain in this worktree local")
    directory.mkdir(parents=True, exist_ok=False)
    database, source, catalog = seed(directory, args.bundle, args.original)
    if args.seed_only:
        print(canonical({"database": str(database), "profile_version": 12}).decode("ascii")); return
    receipts = []
    with ResearchStore(database, catalog) as store:
        migration = store.migrate_research(source, account_id=source.profile["account_id"], policy=POLICY)
        initial = store.read_profile(source.profile["account_id"])
        resources = store._project_profile(source.profile["account_id"], initial)["resources"]
        chassis = catalog.modules["module:ussr:chassis:T-18Bis"]["native_compact_id"]
        vehicle = catalog.vehicles["vehicle:ussr:SU-18"]["native_compact_id"]
        for index, (command, arguments) in enumerate(((201, [3329, 0, 0]), (302, [SHOP_REVISION, chassis, 1, 0]),
                (101, [1, chassis, 0]), (201, [3329, 1, 0]), (301, [SHOP_REVISION, vehicle, 0, -1])), 1):
            request = dict(account_id=source.profile["account_id"], native_database_id=source.profile["native_database_id"],
                command_key="harness:p09e:" + str(index), expected_revision=store.read_profile(source.profile["account_id"])["revision"],
                wire_revision=index, command=command, arguments=arguments)
            result = native_service(store, request, authenticated_account_id=source.profile["account_id"])
            if result["status"] != "researched": raise ValueError("harness operation rejected")
            receipts.append({"request": request, "result": result})
        published = store.publish(source, source.profile["account_id"], directory / "fixtures")
        final = store.read_profile(source.profile["account_id"])
        if published["profile"]["resources"] != resources: raise ValueError("unexpected financial mutation")
    with ResearchStore(database, catalog) as store:
        for row in receipts:
            value = native_service(store, row["request"], authenticated_account_id=source.profile["account_id"])
            if value != {**row["result"], "replayed": True}: raise ValueError("replay result changed")
        if store.read_profile(source.profile["account_id"]) != final: raise ValueError("restart state changed")
    receipt = {"status": "PASS_AUTOMATIC_SQLITE_NATIVE_ADAPTER", "native_ui": "NOT_RUN", "migration": migration,
        "catalog_sha256": catalog.sha256, "database": str(database), "fixture_dir": published["fixture_dir"],
        "commands": receipts, "initial_revision": initial["revision"], "final_revision": final["revision"],
        "resources_unchanged": True, "restart_replay": True, "battle_admission": False}
    (directory / "receipt.json").write_bytes(canonical(receipt) + b"\n")
    print(canonical({k: v for k, v in receipt.items() if k != "commands"}).decode("ascii"))


if __name__ == "__main__": main()
