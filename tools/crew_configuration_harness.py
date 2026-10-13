"""Run source-bound P04C reservations in one fresh, persistent fixture database.

This is an isolated account/configuration authority scenario. Test inventory,
crew and equipment assignment are explicit fixtures, not native account grants.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import platform
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

from tools.crew_configuration_store import ConfigurationStore
from game_profile_tx import TransactionError
from p09c_ammo_catalog import MOUNTS, SHELLS
from tools.destructible_catalog import no_links, read
from server.domain import crew_equipment as crew


FORMAT = "crew-configuration-harness.v1"
PASS = "PASS_P04C_ISOLATED_CONFIGURATION_RESERVATION"
MAX_EVIDENCE_BYTES = 256 * 1024
OWNER = "fixture-owner:alice"
OTHER = "fixture-owner:bob"
MS1 = "fixture-vehicle:alice-ms1"
IS7 = "fixture-vehicle:alice-is7"
OTHER_MS1 = "fixture-vehicle:bob-ms1"
VENT1 = "optional_device:improvedVentilation_class1"
VENT3 = "optional_device:improvedVentilation_class3"
AIM = "optional_device:enhancedAimDrives"
OPTICS = "optional_device:coatedOptics"


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _save(path, value):
    return _save_bytes(path, crew.canonical(value))


def _save_bytes(path, raw):
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_EVIDENCE_BYTES:
        raise ValueError("harness evidence byte bound exceeded")
    with path.open("xb") as stream:
        stream.write(raw)
    return {"bytes": len(raw), "sha256": _sha(raw)}


def fixture_configuration(account, vehicle_id, assembly, devices):
    """Known synthetic ownership, with actual audited component/role sources."""
    vehicle = next(item for item in crew.VEHICLES if item.definition_id == assembly.vehicle_definition_id)
    return crew.canonical({
        "format": crew.FORMAT, "policy": crew.POLICY, "account_id": account,
        "vehicle_inventory_id": vehicle_id, "vehicle_definition_id": vehicle.definition_id,
        "configuration_revision": 1, "component_configuration_sha256": assembly.sha256,
        "crew": [{"crew_id": vehicle_id + ":crew-" + str(seat), "seat": seat,
                  "role": roles[0], "role_level": 100,
                  "trained_vehicle_definition_id": vehicle.definition_id,
                  "vehicle_inventory_id": vehicle_id, "healthy": True, "skills": []}
                 for seat, roles in enumerate(vehicle.seats)],
        "optional_devices": devices,
    })


def run(config_path: Path, out: Path) -> dict:
    config_path = no_links(config_path)
    out = no_links(out)
    allowed = no_links(ROOT / "local/evidence")
    if not config_path.is_file():
        raise ValueError("explicit existing local configuration required")
    if not out.is_relative_to(allowed) or out == allowed or out.exists():
        raise ValueError("fresh child directory under this worktree local/evidence required")
    out.mkdir(parents=True, exist_ok=False)
    database = out / "isolated-configuration.sqlite3"
    artifacts, checks, states, results = {}, {}, [], {}
    configuration_raw = {}

    def save(name, value):
        artifacts[name] = _save(out / name, value)

    def footprint(store):
        return {"alice": store.read_profile(OWNER), "bob": store.read_profile(OTHER),
                "alice_ledger": store.ledger_count(OWNER), "bob_ledger": store.ledger_count(OTHER)}

    def observe(store, label, expected_revision, expected_ledger):
        profile = store.read_profile(OWNER)
        ledger = store.ledger_count(OWNER)
        checks[label + "_revision_and_ledger"] = profile["revision"] == expected_revision and ledger == expected_ledger
        states.append({"step": label, "revision": profile["revision"], "ledger_count": ledger,
                       "profile_sha256": _sha(crew.canonical(profile)), "depot": profile["depot"],
                       "vehicles": profile["vehicles"]})
        return profile

    def reject(store, label, code, function, **arguments):
        before = footprint(store)
        try:
            function(**arguments)
        except TransactionError as error:
            checks[label] = error.code == code and footprint(store) == before
            results[label] = {"status": "REJECTED", "code": error.code}
        else:
            checks[label] = False
            results[label] = {"status": "UNEXPECTED_ACCEPTANCE"}

    ms1_shell = MOUNTS["ms1-stock"].shell_ids[0]
    is7_ap, is7_apcr, _is7_he = MOUNTS["is7-stock"].shell_ids
    service_ms1 = dict(authenticated_account_id=OWNER, account_id=OWNER, command_id="fixture-service-ms1",
                       vehicle_id=MS1, expected_revision=0, desired={ms1_shell: 20})
    service_is7 = dict(authenticated_account_id=OWNER, account_id=OWNER, command_id="fixture-service-is7",
                       vehicle_id=IS7, expected_revision=1, desired={is7_ap: 15})
    change_is7 = dict(authenticated_account_id=OWNER, account_id=OWNER, command_id="fixture-change-is7",
                      vehicle_id=IS7, expected_revision=3, desired={is7_ap: 14, is7_apcr: 1})

    # Constructor rehashes all required original/native resources before opening
    # this path; a failed source activation cannot create the SQLite database.
    with ConfigurationStore(database, config_path=config_path) as store:
        store.initialize()
        save("crew-source-audit.json", store.crew_source_receipt)
        save("ammo-source-audit.json", store.ammo_source_receipt)
        save("mass-source-audit.json", {"format": FORMAT,
             "assemblies": [{"sha256": item.sha256, "evidence_sha256": item.evidence_sha256,
                             "evidence": item.evidence_dict()} for item in store.assemblies.values()]})
        store.create_profile(OWNER, (MS1, IS7))
        store.create_profile(OTHER, (OTHER_MS1,))
        for account, mounts in ((OWNER, {MS1: "ms1-stock", IS7: "is7-stock"}),
                                (OTHER, {OTHER_MS1: "ms1-stock"})):
            store.seed_test_ammunition(account, mounts, {shell: 300 for shell in SHELLS})
            configurations = {}
            for vehicle_id, mount_id in mounts.items():
                devices = [VENT1, OPTICS, None] if mount_id == "ms1-stock" else [VENT3, AIM, OPTICS]
                raw = fixture_configuration(account, vehicle_id, store.assemblies[mount_id], devices)
                configurations[vehicle_id] = raw
                configuration_raw[vehicle_id] = raw
            store.seed_test_configurations(account, configurations)
        initial = footprint(store)
        save("fixture-initial-profiles.json", initial)
        observe(store, "fixture_seed", 0, 0)
        configuration_shas = {row["vehicle_id"]: row["configuration_sha256"]
                              for row in initial["alice"]["configurations"]}
        checks["source_bound_fixture_bytes"] = all(configuration_shas[key] == _sha(configuration_raw[key])
                                                   for key in (MS1, IS7))
        reserve_ms1 = dict(authenticated_account_id=OWNER, account_id=OWNER, command_id="fixture-reserve-ms1",
                           vehicle_id=MS1, expected_revision=2, expected_configuration_sha256=configuration_shas[MS1],
                           battle_id="fixture-battle:ms1")
        reserve_is7 = dict(authenticated_account_id=OWNER, account_id=OWNER, command_id="fixture-reserve-is7",
                           vehicle_id=IS7, expected_revision=4, expected_configuration_sha256=configuration_shas[IS7],
                           battle_id="fixture-battle:is7")

        results["service_ms1"] = store.set_ammunition(**service_ms1)
        observe(store, "service_ms1", 1, 1)
        results["service_is7"] = store.set_ammunition(**service_is7)
        observe(store, "service_is7", 2, 2)
        results["reserve_ms1"] = store.reserve_configuration(**reserve_ms1)
        observe(store, "reserve_ms1", 3, 3)
        save("ms1-frozen-configuration.json", results["reserve_ms1"]["frozen"])
        checks["ms1_frozen_sha_matches_canonical_file"] = (
            artifacts["ms1-frozen-configuration.json"]["sha256"] == results["reserve_ms1"]["frozen_sha256"])
        results["change_unreserved_is7"] = store.set_ammunition(**change_is7)
        observe(store, "change_unreserved_is7", 4, 4)
        before = footprint(store)
        results["replay_ms1_after_other_service"] = store.reserve_configuration(**reserve_ms1)
        checks["ms1_replay_after_other_service_same_frozen_no_write"] = (
            results["replay_ms1_after_other_service"] == {**results["reserve_ms1"], "replayed": True}
            and footprint(store) == before)
        observe(store, "replay_ms1_after_other_service", 4, 4)
        results["reserve_is7"] = store.reserve_configuration(**reserve_is7)
        final = observe(store, "reserve_is7", 5, 5)
        save("is7-frozen-configuration.json", results["reserve_is7"]["frozen"])
        checks["is7_frozen_sha_matches_canonical_file"] = (
            artifacts["is7-frozen-configuration.json"]["sha256"] == results["reserve_is7"]["frozen_sha256"])
        checks["frozen_ms1_load_is_20_ap"] = results["reserve_ms1"]["frozen"]["ammunition"]["loaded"][ms1_shell] == 20
        checks["frozen_is7_load_is_14_ap_1_apcr"] = (
            results["reserve_is7"]["frozen"]["ammunition"]["loaded"][is7_ap] == 14
            and results["reserve_is7"]["frozen"]["ammunition"]["loaded"][is7_apcr] == 1)
        checks["actual_ms1_equipment_mass_4791kg"] = (
            results["reserve_ms1"]["frozen"]["crew_equipment"]["mass_check"]["total_mass_grams"] == 4791000)
        checks["actual_is7_equipment_mass_68490kg"] = (
            results["reserve_is7"]["frozen"]["crew_equipment"]["mass_check"]["total_mass_grams"] == 68490000)
        checks["each_shell_conserved"] = all(final["depot"][shell] + sum(
            row["loaded"].get(shell, 0) for row in final["ammunition"]) == 300 for shell in SHELLS)
        checks["bob_fixture_unchanged"] = store.read_profile(OTHER) == initial["bob"] and store.ledger_count(OTHER) == 0
        before_reopen = footprint(store)
        save("profiles-before-reopen.json", before_reopen)

    closed_database_sha = _sha(read(database, 1024 * 1024))
    with ConfigurationStore(database, config_path=config_path) as store:
        store.initialize()
        checks["reopen_profiles_and_ledgers_equal"] = footprint(store) == before_reopen
        for label, request in (("ms1", reserve_ms1), ("is7", reserve_is7)):
            before = footprint(store)
            replay = store.reserve_configuration(**request)
            results["reopen_replay_" + label] = replay
            checks["reopen_" + label + "_same_frozen_no_write"] = (
                replay == {**results["reserve_" + label], "replayed": True} and footprint(store) == before)
            consumer_request = dict(authenticated_account_id=OWNER, account_id=OWNER,
                                    command_id=request["command_id"], battle_id=request["battle_id"],
                                    expected_frozen_sha256=results["reserve_" + label]["frozen_sha256"])
            raw = store.read_reserved_configuration(**consumer_request)
            checks["reopen_" + label + "_consumer_immutable_canonical_bytes_no_write"] = (
                type(raw) is bytes and raw == crew.canonical(results["reserve_" + label]["frozen"])
                and _sha(raw) == consumer_request["expected_frozen_sha256"] and footprint(store) == before)
            filename = label + "-reopened-consumer-snapshot.json"
            artifacts[filename] = _save_bytes(out / filename, raw)
        reject(store, "consumer_foreign_account_rejected_unchanged", "FOREIGN_ACCOUNT",
               store.read_reserved_configuration, **{**consumer_request, "authenticated_account_id": OTHER})
        reject(store, "consumer_wrong_battle_rejected_unchanged", "RESERVATION_BINDING_MISMATCH",
               store.read_reserved_configuration, **{**consumer_request, "battle_id": "fixture-battle:wrong"})
        reject(store, "consumer_wrong_frozen_digest_rejected_unchanged", "RESERVATION_BINDING_MISMATCH",
               store.read_reserved_configuration, **{**consumer_request, "expected_frozen_sha256": "0" * 64})
        for label, request in (("ms1", service_ms1), ("is7", service_is7)):
            before = footprint(store)
            replay = store.set_ammunition(**request)
            results["reopen_service_replay_" + label] = replay
            checks["service_replay_" + label + "_no_double_debit"] = (
                replay == {**results["service_" + label], "replayed": True} and footprint(store) == before)
        reject(store, "reserved_ms1_service_rejected_unchanged", "VEHICLE_RESERVED", store.set_ammunition,
               **{**service_ms1, "command_id": "fixture-rejected-service-ms1", "expected_revision": 5})
        reject(store, "reserved_is7_service_rejected_unchanged", "VEHICLE_RESERVED", store.set_ammunition,
               **{**change_is7, "command_id": "fixture-rejected-service-is7", "expected_revision": 5})
        reject(store, "foreign_account_replay_rejected_unchanged", "FOREIGN_ACCOUNT", store.reserve_configuration,
               **{**reserve_ms1, "authenticated_account_id": OTHER})
        reject(store, "changed_replay_payload_rejected_unchanged", "DUPLICATE_PAYLOAD_MISMATCH", store.reserve_configuration,
               **{**reserve_ms1, "battle_id": "fixture-battle:changed"})
        observe(store, "reopen_replays_and_rejections", 5, 5)
        save("fixture-final-profiles.json", footprint(store))

    checks["replays_and_rejections_preserve_database_bytes"] = _sha(read(database, 1024 * 1024)) == closed_database_sha
    save("scenario-observations.json", {"states": states, "command_results": results})
    database_raw = read(database, 1024 * 1024)
    artifacts[database.name] = {"bytes": len(database_raw), "sha256": _sha(database_raw)}
    receipt = {"format": FORMAT, "status": PASS if checks and all(checks.values()) else "FAIL",
               "checks": checks, "database": database.name, "artifacts": artifacts,
               "platform": {"platform": platform.platform(), "python": platform.python_version(),
                            "architecture": platform.machine(), "sqlite": sqlite3.sqlite_version},
               "code_sha256": {name: _sha(read(ROOT / name, 2 * 1024 * 1024)) for name in (
                   "tools/crew_configuration_harness.py", "tools/crew_configuration_store.py",
                   "tools/crew_equipment_mass.py", "tools/crew_equipment_source_audit.py",
                   "server/domain/crew_equipment.py", "tools/game_profile_tx.py",
                   "tools/p09c_ammo_service.py", "tools/p09c_ammo_catalog.py",
                   "tools/packed_xml.py", "tools/py27_static.py", "tools/destructible_catalog.py")},
               "fixture_ownership": "ISOLATED_SYNTHETIC_ACCOUNTS_CREW_EQUIPMENT_AND_DEPOT_ONLY",
               "fixture_depot": "300 of each of six source-bound shell definitions per fixture account",
               "classification": "OBSERVED_ISOLATED_SQLITE_WITH_VERIFIED_717_STATIC_SOURCES",
               "runtime_wiring": "NOT_RUN", "native_acceptance": "NOT_RUN", "live_inventory_grant": "NOT_RUN",
               "historical_crew_combat_formulas": "UNKNOWN_UNSUPPORTED",
               "rollback": "No deployed state changed; preserve evidence or remove only this isolated output directory"}
    _save(out / "receipt.json", receipt)
    return receipt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        receipt = run(args.config, args.out)
    except (ValueError, OSError, TransactionError, sqlite3.Error) as error:
        parser.exit(1, f"FAIL_P04C_CONFIGURATION_HARNESS: {error}\n")
    print(json.dumps({"status": receipt["status"], "checks": len(receipt["checks"]),
                      "receipt": str(no_links(args.out) / "receipt.json"),
                      "receipt_sha256": _sha(read(no_links(args.out) / "receipt.json", MAX_EVIDENCE_BYTES))}, sort_keys=True))
    return 0 if receipt["status"] == PASS else 1


if __name__ == "__main__":
    raise SystemExit(main())
