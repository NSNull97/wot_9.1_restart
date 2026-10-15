"""Trusted configured bridge worker: profile13 hangar and battle, same SQLite."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from p08b_battle_store import POLICY_SHA256, REJECTIONS, validate_request
from p08c_battle_results import ResultsStore as BattleStore, results_service
from p08b_battle_projection import BattleProjectionSource, capabilities
from p09e_research_store import POLICY as RESEARCH_POLICY
from p09e_research_catalog import load_catalog
from p09e_native_research_audit import audit
from p09e_research_service import native_service, existing_service, CREW_OPERATIONS
from p09d_ammo_projection import canonical
from game_profile_tx import TransactionError
from destructible_catalog import json_value


def battle_service(store, request, *, authenticated_account_id):
    """Domain denials are explicit; auth, corruption and malformed data fail closed."""
    request = validate_request(request, authenticated_account_id)
    try: return store.battle(request, authenticated_account_id=authenticated_account_id)
    except TransactionError as error:
        if error.code not in REJECTIONS: raise
        aggregate = store.read_profile(authenticated_account_id)
        return store._reply(request, aggregate["revision"], "rejected", code=error.code)


def main():
    from p08b_owner_source import projection_source
    from p04m_pool_store import PoolStore
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("database", "bundle", "original-root", "account-id", "fixture-root"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("operation", choices=("activate", "fixture", "overview", "pool-activate", "pool-overview", "battle", "results", "research", *CREW_OPERATIONS))
    args = parser.parse_args()
    catalog = load_catalog(args.original_root)
    audit(args.original_root)
    with PoolStore(args.database, catalog, account_id=args.account_id) as store:
        if args.operation == "activate":
            source = projection_source(args.bundle, catalog, args.database, args.account_id)
            store._allow_prebattle = True
            try: store.migrate_research(source, account_id=args.account_id, policy=RESEARCH_POLICY)
            finally: store._allow_prebattle = False
            result = store.activate(account_id=args.account_id, authenticated_account_id=args.account_id)
            result.update(store.publish(source, args.account_id, args.fixture_root))
        elif args.operation == "fixture":
            store.initialize()
            result = store.publish(projection_source(args.bundle, catalog, args.database, args.account_id), args.account_id, args.fixture_root)
        elif args.operation == "overview":
            aggregate = store.read_profile(args.account_id)
            result = {"profile": store._project_profile(args.account_id, aggregate), "revision": aggregate["revision"],
                "policy_sha256": POLICY_SHA256, "capabilities": capabilities(catalog, aggregate)}
        elif args.operation == "pool-overview":
            from p04m_pool_store import POLICY_SHA256 as POOL_POLICY_SHA256
            from p04m_stock_registry import SCHEMA as POOL_SCHEMA, DEFINITION_SHA256
            aggregate = store.read_profile(args.account_id)
            result = dict(version=1, schema=POOL_SCHEMA, definition_sha256=DEFINITION_SHA256,
                registry_sha256=store.registry.sha256, policy_sha256=POOL_POLICY_SHA256, active=store.pool_active(),
                capabilities=store.registry.capabilities(aggregate))
        else:
            store.initialize()
            limit = 65536 if args.operation in ("results", "battle") else 4096
            raw = sys.stdin.buffer.read(limit + 1)
            request = json_value(raw, limit=limit, nodes=64, depth=4)
            if args.operation == "pool-activate": result = store.activate_pool(request, authenticated_account_id=args.account_id)
            elif args.operation == "battle": result = battle_service(store, request, authenticated_account_id=args.account_id)
            elif args.operation == "results": result = results_service(store, request, authenticated_account_id=args.account_id)
            elif args.operation == "research": result = native_service(store, request, authenticated_account_id=args.account_id)
            else: result = existing_service(store, args.operation, request, authenticated_account_id=args.account_id)
        print(canonical(result).decode("ascii"))


if __name__ == "__main__":
    try: main()
    except Exception as error:
        print(type(error).__name__ + ": " + str(error), file=sys.stderr)
        raise SystemExit(1)
