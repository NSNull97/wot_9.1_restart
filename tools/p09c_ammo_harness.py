"""Run one source-audited P09C scenario in a fresh local evidence directory."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import platform
import sqlite3

from game_profile_tx import TransactionError
from p09c_ammo_catalog import MOUNTS, SHELLS, audit_sources
from p09c_ammo_service import AmmoServiceStore
from destructible_catalog import no_links

ROOT = Path(__file__).resolve().parents[1]


def _save(path: Path, value: dict) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write("\n")


def run(original_root: Path, out: Path) -> dict:
    out = no_links(out)
    allowed = no_links(ROOT / "local" / "evidence")
    if not out.is_relative_to(allowed) or out == allowed or out.exists():
        raise ValueError("new child directory under this worktree local/evidence required")
    # No DB or success receipt is created if source pins fail.
    source_audit = audit_sources(original_root)
    out.mkdir(parents=True, exist_ok=False)
    _save(out / "source-audit.json", source_audit)
    db = out / "isolated-ammo.sqlite3"
    account = "p09c-isolated-owner"
    ms1, is7 = MOUNTS["ms1-stock"], MOUNTS["is7-stock"]
    checks = {}
    observations = {}

    def command(store, **changes):
        args = dict(authenticated_account_id=account, account_id=account,
                    command_id="service-is7", vehicle_id="test-is7", expected_revision=0,
                    desired={is7.shell_ids[0]: 24, is7.shell_ids[1]: 4, is7.shell_ids[2]: 2})
        args.update(changes)
        return store.set_ammunition(**args)

    def rejected(store, code, **changes):
        before = store.read_profile(account)
        ledger = store.ledger_count(account)
        try:
            command(store, **changes)
        except TransactionError as error:
            return error.code == code and before == store.read_profile(account) and ledger == store.ledger_count(account)
        return False

    with AmmoServiceStore(db) as store:
        store.initialize()
        store.create_profile(account, ("test-ms1", "test-is7"))
        store.seed_test_ammunition(account, {"test-ms1": ms1.mount_id, "test-is7": is7.mount_id},
                                   {shell: 100 for shell in SHELLS})
        observations["initial"] = store.read_profile(account)
        checks["foreign_account_unchanged"] = rejected(store, "FOREIGN_ACCOUNT", authenticated_account_id="other")
        checks["incompatible_shell_unchanged"] = rejected(store, "INCOMPATIBLE_SHELL", desired={ms1.shell_ids[0]: 1})
        checks["capacity_unchanged"] = rejected(store, "CAPACITY_EXCEEDED", desired={is7.shell_ids[0]: 31})
        checks["purchase_unavailable_unchanged"] = rejected(store, "PURCHASE_UNSUPPORTED", funding="credits")
        first = command(store)
        observations["first"] = first
        checks["is7_full_capacity_committed"] = sum(first["loaded"].values()) == is7.capacity
        after = store.read_profile(account)
        replay = command(store)
        checks["exact_replay_no_double_debit"] = replay == {**first, "replayed": True} and after == store.read_profile(account) and store.ledger_count(account) == 1
        checks["stale_revision_unchanged"] = rejected(store, "STALE_REVISION", command_id="stale")
        checks["changed_replay_unchanged"] = rejected(store, "DUPLICATE_PAYLOAD_MISMATCH", desired={is7.shell_ids[0]: 20})
        store.failpoint = "before_commit"
        checks["precommit_rollback"] = rejected(store, "INJECTED_FAILURE", command_id="rollback", expected_revision=1, desired={is7.shell_ids[0]: 20})
        store.failpoint = None
        second = command(store, command_id="change-is7", expected_revision=1,
                         desired={is7.shell_ids[0]: 20, is7.shell_ids[2]: 10})
        observations["change"] = second
        third = command(store, command_id="service-ms1", vehicle_id="test-ms1", expected_revision=2,
                        desired={ms1.shell_ids[0]: 96})
        observations["ms1"] = third
        checks["ms1_full_capacity_committed"] = sum(third["loaded"].values()) == ms1.capacity
        final = store.read_profile(account)
        checks["each_shell_conserved"] = all(
            final["depot"][shell] + sum(row["loaded"].get(shell, 0) for row in final["ammunition"]) == 100
            for shell in SHELLS
        )
        observations["before_reopen"] = final
    with AmmoServiceStore(db) as store:
        store.initialize()
        checks["reopen_snapshot_equal"] = store.read_profile(account) == observations["before_reopen"]
        replay = command(store)
        checks["reopen_original_replay_after_later_changes"] = replay == {**first, "replayed": True} and store.read_profile(account) == final
        reservation = store.reserve_vehicle(account_id=account, command_id="reserve-is7",
                                            vehicle_id="test-is7", expected_revision=3, battle_id="isolated-battle")
        observations["reservation"] = reservation
        checks["shared_reservation_revision"] = reservation["destination_revision"] == 4
        checks["reserved_service_unchanged"] = rejected(store, "VEHICLE_RESERVED", command_id="reserved", expected_revision=4)
        observations["final"] = store.read_profile(account)
        checks["shared_ledger_count"] = store.ledger_count(account) == 4
    _save(out / "observations.json", observations)
    receipt = {"schema": "p09c-ammo-harness.v1",
               "status": "PASS_P09C_ISOLATED_AMMO_SERVICE" if all(checks.values()) else "FAIL",
               "checks": checks, "db": str(db),
               "platform": platform.platform(), "python": platform.python_version(),
               "sqlite": sqlite3.sqlite_version,
               "source_sha256": {name: hashlib.sha256((ROOT / "tools" / name).read_bytes()).hexdigest()
                                 for name in ("p09c_ammo_catalog.py", "p09c_ammo_service.py",
                                              "p09c_ammo_harness.py", "game_profile_tx.py",
                                              "packed_xml.py", "py27_static.py", "destructible_catalog.py")},
               "artifacts": {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                             for path in (out / "source-audit.json", out / "observations.json", db)},
               "runtime_wiring": "NOT_RUN", "native_service_and_is7_loadout": "NOT_RUN",
               "prices_purchases_repair_consumables": "UNSUPPORTED"}
    _save(out / "receipt.json", receipt)
    return receipt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--original-root", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)
    result = run(args.original_root, args.out)
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] == "PASS_P09C_ISOLATED_AMMO_SERVICE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
