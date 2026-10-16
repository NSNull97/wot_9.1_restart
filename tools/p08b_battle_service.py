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
    if type(request)is dict and type(request.get("version"))is int and request["version"]==4:
        from p06t_ammo_loss_store import battle_loss_service
        return battle_loss_service(store,request,authenticated_account_id=authenticated_account_id)
    if type(request)is dict and type(request.get("version"))is int and request["version"]==2:
        from p06t_mixed_store import MixedAmmoStore, validate_request as mixed_request, REJECTIONS as mixed_rejections
        if not isinstance(store,MixedAmmoStore):raise TransactionError("P06T_ACTIVATION_REQUIRED")
        request=mixed_request(request,authenticated_account_id)
        try:return store.battle(request,authenticated_account_id=authenticated_account_id)
        except TransactionError as error:
            if error.code not in mixed_rejections|{"RESULT_MISMATCH","INVALID_TERMINAL_STATE"}:raise
            aggregate=store.read_profile(authenticated_account_id)
            return store._mixed_reply(request,aggregate["revision"],"rejected",code=error.code)
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
    parser.add_argument("--mixed-ammo",action="store_true",help="Explicit version2 owned mixed-ammunition worker")
    parser.add_argument("--ammo-rack-loss",action="store_true",help="Explicit version4 owned ammo-rack loss accounting")
    parser.add_argument("--shell-catalog")
    parser.add_argument("--terminal-policy")
    parser.add_argument("operation", choices=("activate", "fixture", "overview", "pool-activate", "pool-overview", "mixed-activate", "mixed-overview", "loss-activate", "battle", "results", "research", *CREW_OPERATIONS))
    args = parser.parse_args()
    if args.mixed_ammo != bool(args.shell_catalog and args.terminal_policy) or (not args.mixed_ammo and (args.shell_catalog or args.terminal_policy)):
        parser.error("--mixed-ammo requires both trusted source files; source paths require the explicit opt-in")
    if args.ammo_rack_loss and not args.mixed_ammo:parser.error("--ammo-rack-loss requires --mixed-ammo and its trusted sources")
    catalog = load_catalog(args.original_root)
    audit(args.original_root)
    if args.mixed_ammo:
        if args.ammo_rack_loss:from p06t_ammo_loss_store import AmmoLossStore as MixedAmmoStore
        else:from p06t_mixed_store import MixedAmmoStore
        factory=lambda:MixedAmmoStore(args.database,catalog,account_id=args.account_id,shell_catalog=args.shell_catalog,terminal_policy=args.terminal_policy)
    else:factory=lambda:PoolStore(args.database,catalog,account_id=args.account_id)
    with factory() as store:
        if args.mixed_ammo and args.operation!="mixed-activate" and not store.mixed_active():raise TransactionError("P06T_ACTIVATION_REQUIRED")
        if args.ammo_rack_loss and args.operation!="loss-activate" and not store.loss_active():raise TransactionError("AMMO_LOSS_POLICY_REQUIRED")
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
        elif args.operation == "mixed-overview":
            if not args.mixed_ammo:raise TransactionError("P06T_ACTIVATION_REQUIRED")
            from p06t_mixed_store import POLICY_SHA256 as mixed_sha,SCHEMA as mixed_schema,SOURCE_SHA256
            aggregate=store.read_profile(args.account_id)
            result=dict(version=2,schema=mixed_schema,policy_sha256=mixed_sha,shell_catalog_sha256=SOURCE_SHA256,
                account_id=args.account_id,native_database_id=store._project_profile(args.account_id,aggregate)["native_database_id"],revision=aggregate["revision"],active=store.mixed_active())
        else:
            store.initialize()
            limit = 65536 if args.operation in ("results", "battle") else 4096
            raw = sys.stdin.buffer.read(limit + 1)
            request = json_value(raw, limit=limit, nodes=64, depth=4)
            if args.operation=="loss-activate":
                from p06t_ammo_loss_store import AmmoLossStore,CONTRACT,POLICY_SHA256 as loss_sha
                from p09d_ammo_store import require
                require(args.ammo_rack_loss and isinstance(store,AmmoLossStore) and set(request)=={"version","contract","account_id","native_database_id","expected_revision","policy_sha256"}
                    and type(request["version"])is int and request["version"]==4 and request["contract"]==CONTRACT
                    and request["account_id"]==args.account_id and request["policy_sha256"]==loss_sha,"INVALID_INPUT")
                from p08b_battle_store import _integer
                _integer(request["native_database_id"],1);_integer(request["expected_revision"],13)
                result=store.activate_loss(account_id=args.account_id,authenticated_account_id=args.account_id,
                    expected_revision=request["expected_revision"],native_database_id=request["native_database_id"])
            elif args.operation=="mixed-activate":
                if not args.mixed_ammo:raise TransactionError("P06T_ACTIVATION_REQUIRED")
                from p06t_mixed_store import POLICY_SHA256 as mixed_sha,SOURCE_SHA256
                from p06t_terminal import MANIFEST_SHA256
                from p08b_battle_store import _integer,_uuid
                from p09d_ammo_store import require
                require(set(request)=={"version","account_id","native_database_id","expected_revision","policy_sha256","shell_catalog_sha256","terminal_policy_sha256"}
                    and type(request["version"])is int and request["version"]==2 and request["account_id"]==args.account_id
                    and request["policy_sha256"]==mixed_sha and request["shell_catalog_sha256"]==SOURCE_SHA256
                    and request["terminal_policy_sha256"]==MANIFEST_SHA256,"INVALID_INPUT")
                _uuid(args.account_id);_integer(request["native_database_id"],1);_integer(request["expected_revision"],13)
                result=store.activate_mixed(account_id=args.account_id,authenticated_account_id=args.account_id,
                    expected_revision=request["expected_revision"],native_database_id=request["native_database_id"])
            elif args.operation == "pool-activate": result = store.activate_pool(request, authenticated_account_id=args.account_id)
            elif args.operation == "battle": result = battle_service(store, request, authenticated_account_id=args.account_id)
            elif args.operation == "results":
                if args.ammo_rack_loss and request.get("version")==4:
                    from p06t_ammo_loss_store import results_loss_service
                    result=results_loss_service(store,request,authenticated_account_id=args.account_id)
                elif args.mixed_ammo and request.get("version")==2:
                    from p06t_mixed_store import results_service_mixed
                    result=results_service_mixed(store,request,authenticated_account_id=args.account_id)
                else:result = results_service(store, request, authenticated_account_id=args.account_id)
            elif args.operation == "research": result = native_service(store, request, authenticated_account_id=args.account_id)
            else: result = existing_service(store, args.operation, request, authenticated_account_id=args.account_id)
        print(canonical(result).decode("ascii"))


if __name__ == "__main__":
    try: main()
    except Exception as error:
        print(type(error).__name__ + ": " + str(error), file=sys.stderr)
        raise SystemExit(1)
