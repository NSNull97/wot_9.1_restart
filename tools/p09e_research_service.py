"""Explicit same-store P09E worker; no daemon, installation or live activation.

The trusted loopback bridge supplies the authenticated account. Input JSON
cannot select another account, source path, policy, catalogue or database.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from p09e_research_catalog import load_catalog
from p09e_research_store import ResearchStore, POLICY, POLICY_SHA256
from p09e_research_projection import ResearchProjectionSource, SHOP_REVISION, update_delta
from p09e_native_commands import NativeRequest, domain_request, validate_selection
from p09e_native_research_audit import audit
from p09d_ammo_projection import canonical
from p09d_ammo_store import sha, require
from game_profile_tx import TransactionError, _bounded_id, _revision
from destructible_catalog import json_value

FIELDS = {"account_id", "native_database_id", "command_key", "expected_revision", "wire_revision", "command", "arguments"}
REJECTIONS = frozenset({"INVALID_NATIVE_REQUEST", "UNKNOWN_VEHICLE", "UNKNOWN_MODULE", "UNOWNED_VEHICLE",
    "UNEXPECTED_GUN_SELECTION", "INVALID_GUN_SELECTION", "SHOP_REVISION_MISMATCH", "AUTOBUY_CREW_SHELLS_UNSUPPORTED",
    "GOLD_CONVERSION_UNSUPPORTED", "PAID_OR_SLOT_OPERATION_UNSUPPORTED", "UNKNOWN_VEHICLE_TYPE", "VEHICLE_NOT_RESEARCHED",
    "UNKNOWN_UNLOCK", "MISSING_PREREQUISITE", "ALREADY_RESEARCHED", "VEHICLE_ACQUISITION_UNSUPPORTED",
    "UNSUPPORTED_CONFIGURATION", "GOLD_PURCHASE_UNSUPPORTED", "VEHICLE_ALREADY_OWNED", "GARAGE_LIMIT",
    "INTERNAL_COMPONENT_UNSUPPORTED", "MODULE_NOT_RESEARCHED", "DEPOT_OVERFLOW", "VEHICLE_RESERVED",
    "DUPLICATE_MODULE_SLOT", "INCOMPATIBLE_MODULE", "INCOMPATIBLE_TURRET_GUN", "CHASSIS_OVERLOAD",
    "NO_CONFIGURATION_CHANGE", "UNLOAD_AMMUNITION_REQUIRED", "MODULE_NOT_OWNED", "INVALID_INPUT"})
GARAGE_REJECTIONS = REJECTIONS | frozenset({"AMMUNITION_CONFIGURATION_UNSUPPORTED", "PURCHASE_UNSUPPORTED",
    "CAPACITY_EXCEEDED", "INSUFFICIENT_STOCK", "INCOMPATIBLE_SHELL", "UNSUPPORTED_MOUNT",
    "FREE_RECRUITMENT_EXHAUSTED", "RECRUIT_SELECTION_UNSUPPORTED", "TRANSFER_SELECTION_UNSUPPORTED",
    "UNKNOWN_TANKMAN", "INCOMPATIBLE_CREW_ROLE", "BARRACKS_FULL", "INVALID_QUANTITY"})


def existing_service(store, operation, request, *, authenticated_account_id):
    """Keep inherited garage rejections explicit; integrity/auth errors stay fatal."""
    require(operation in ("service", "transfer", "recruit"))
    require(type(request) is dict and request.get("account_id") == authenticated_account_id, "FOREIGN_ACCOUNT")
    _bounded_id(request.get("command_key"), "command_key")
    _revision(request.get("expected_revision"))
    require(type(request.get("wire_revision")) is int and 1 <= request["wire_revision"] < 2**31 - 1)
    current = store.read_profile(authenticated_account_id)
    public = store._project_profile(authenticated_account_id, current)
    require(type(request.get("native_database_id")) is int
        and public["native_database_id"] == request["native_database_id"], "FOREIGN_ACCOUNT")
    try:
        return getattr(store, operation)(request, authenticated_account_id=authenticated_account_id)
    except TransactionError as error:
        if error.code not in GARAGE_REJECTIONS: raise
        current = store.read_profile(authenticated_account_id)
        require(current["revision"] == request["expected_revision"], "STALE_REVISION")
        return dict(status="rejected", account_id=authenticated_account_id,
            native_database_id=request["native_database_id"], command_key=request["command_key"],
            revision=current["revision"], wire_revision=request["wire_revision"],
            update_hex="", replayed=False, result_code=-10)


def native_service(store, request, *, authenticated_account_id):
    require(type(request) is dict and set(request) == FIELDS)
    require(request["account_id"] == authenticated_account_id, "FOREIGN_ACCOUNT")
    _bounded_id(request["command_key"], "command_key")
    _revision(request["expected_revision"])
    require(type(request["wire_revision"]) is int and 1 <= request["wire_revision"] < 2**31 - 1)
    require(type(request["native_database_id"]) is int and 1 <= request["native_database_id"] < 2**31)
    require(type(request["command"]) is int and type(request["arguments"]) is list
            and len(request["arguments"]) <= 6 and all(type(v) is int and -(2**63) <= v < 2**63 for v in request["arguments"]))
    aggregate = store.read_profile(authenticated_account_id)
    public = store._project_profile(authenticated_account_id, aggregate)
    require(public["native_database_id"] == request["native_database_id"], "FOREIGN_ACCOUNT")
    selected = NativeRequest(1, request["command"], tuple(request["arguments"]))
    response = {"status": "researched", "account_id": authenticated_account_id,
        "native_database_id": request["native_database_id"], "command_key": request["command_key"],
        "revision": request["expected_revision"] + 1, "wire_revision": request["wire_revision"] + 1,
        "update_hex": "", "replayed": False, "result_code": 0}
    try:
        validate_selection(selected, shop_revision=SHOP_REVISION)
        domain = domain_request(selected, catalog=store.catalog, aggregate=aggregate,
            account_id=authenticated_account_id, command_key=request["command_key"],
            expected_revision=request["expected_revision"], shop_revision=SHOP_REVISION)
        def project(before, after, result):
            value = dict(response)
            value["revision"] = result["revision"]
            value["update_hex"] = update_delta(store.catalog, before["research"], after["research"], request["wire_revision"]).hex()
            return value
        return store.execute(domain, authenticated_account_id=authenticated_account_id,
            native_binding=sha(canonical(request)), prepare_response=project)
    except TransactionError as error:
        if error.code not in REJECTIONS: raise
        current = store.read_profile(authenticated_account_id)
        require(current["revision"] == request["expected_revision"], "STALE_REVISION")
        return {**response, "status": "rejected", "revision": current["revision"],
            "wire_revision": request["wire_revision"], "update_hex": "", "result_code": -10}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("database", "bundle", "original-root", "account-id", "fixture-root"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("operation", choices=("activate", "fixture", "research", "service", "transfer", "recruit"))
    args = parser.parse_args()
    catalog = load_catalog(args.original_root)
    audit(args.original_root)
    with ResearchStore(args.database, catalog) as store:
        if args.operation == "activate":
            source = ResearchProjectionSource(args.bundle, catalog)
            result = store.migrate_research(source, account_id=args.account_id, policy=POLICY)
            result.update(store.publish(source, args.account_id, args.fixture_root))
        elif args.operation == "fixture":
            store.initialize()
            result = store.publish(ResearchProjectionSource(args.bundle, catalog), args.account_id, args.fixture_root)
        else:
            store.initialize()
            raw = sys.stdin.buffer.read(4097)
            request = json_value(raw, limit=4096, nodes=64, depth=4)
            if args.operation == "research": result = native_service(store, request, authenticated_account_id=args.account_id)
            else: result = existing_service(store, args.operation, request, authenticated_account_id=args.account_id)
        print(canonical(result).decode("ascii"))


if __name__ == "__main__":
    try: main()
    except Exception as error:
        print(type(error).__name__ + ": " + str(error), file=sys.stderr)
        raise SystemExit(1)
