"""Trusted configured bridge worker: profile13 hangar and battle, same SQLite."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = next(p for p in Path(__file__).resolve().parents if (p / 'docs/ACTIVE_GATE.md').is_file() and (p / 'tools/packed_xml.py').is_file())
sys.path[:0] = [str(Path(__file__).resolve().parent), str(ROOT / 'tools'), str(ROOT)]
from p08b_battle_store import POLICY_SHA256, REJECTIONS, validate_request, MAX_RESULT_REQUEST
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
    if type(request)is dict and type(request.get("version"))is int and request["version"]==5:
        from p08b_owner_hold_store import battle_hold_service
        return battle_hold_service(store,request,authenticated_account_id=authenticated_account_id)
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


class WorkerContext:
    """Trusted, already validated worker configuration plus the catalogue it loaded.

    One context serves one account. The CLI builds it per process; the
    long-lived Domain service builds it once and reuses the same catalogue.
    """
    def __init__(self, *, database, bundle, original_root, account_id, fixture_root, mixed_ammo=False,
                 owner_battle_hold=False, ammo_rack_loss=False, shell_catalog=None, terminal_policy=None, catalog):
        self.database, self.bundle, self.original_root = database, bundle, original_root
        self.account_id, self.fixture_root = account_id, fixture_root
        self.mixed_ammo, self.owner_battle_hold, self.ammo_rack_loss = mixed_ammo, owner_battle_hold, ammo_rack_loss
        self.shell_catalog, self.terminal_policy, self.catalog = shell_catalog, terminal_policy, catalog


OPERATIONS = ("activate", "fixture", "overview", "pool-activate", "pool-overview", "mixed-activate", "mixed-overview",
              "loss-activate", "hold-activate", "battle", "results", "research", *CREW_OPERATIONS)
# Operations that take no request body (stdin is not read).
BODYLESS_OPERATIONS = frozenset({"activate", "fixture", "overview", "pool-overview", "mixed-overview"})


def request_limit(operation):
    return MAX_RESULT_REQUEST if operation in ("results", "battle") else 4096


def execute(args, operation, read_request):
    """Run one operation; ``read_request(limit)`` returns the raw request bytes (at most limit+1)."""
    from p08b_owner_source import projection_source
    from p04m_pool_store import PoolStore
    catalog = args.catalog
    if args.mixed_ammo:
        if args.owner_battle_hold:from p08b_owner_hold_store import OwnerHoldStore as MixedAmmoStore
        elif args.ammo_rack_loss:from p06t_ammo_loss_store import AmmoLossStore as MixedAmmoStore
        else:from p06t_mixed_store import MixedAmmoStore
        factory=lambda:MixedAmmoStore(args.database,catalog,account_id=args.account_id,shell_catalog=args.shell_catalog,terminal_policy=args.terminal_policy)
    else:factory=lambda:PoolStore(args.database,catalog,account_id=args.account_id)
    with factory() as store:
        if args.owner_battle_hold and operation!="hold-activate" and not store.hold_active():raise TransactionError("OWNER_HOLD_POLICY_REQUIRED")
        if args.mixed_ammo and operation!="mixed-activate" and not store.mixed_active():raise TransactionError("P06T_ACTIVATION_REQUIRED")
        if args.ammo_rack_loss and operation!="loss-activate" and not store.loss_active():raise TransactionError("AMMO_LOSS_POLICY_REQUIRED")
        if operation == "activate":
            source = projection_source(args.bundle, catalog, args.database, args.account_id)
            store._allow_prebattle = True
            try: store.migrate_research(source, account_id=args.account_id, policy=RESEARCH_POLICY)
            finally: store._allow_prebattle = False
            result = store.activate(account_id=args.account_id, authenticated_account_id=args.account_id)
            result.update(store.publish(source, args.account_id, args.fixture_root))
        elif operation == "fixture":
            store.initialize()
            result = store.publish(projection_source(args.bundle, catalog, args.database, args.account_id), args.account_id, args.fixture_root)
        elif operation == "overview":
            aggregate = store.read_profile(args.account_id)
            result = {"profile": store._project_profile(args.account_id, aggregate), "revision": aggregate["revision"],
                "policy_sha256": POLICY_SHA256, "capabilities": capabilities(catalog, aggregate)}
        elif operation == "pool-overview":
            from p04m_pool_store import POLICY_SHA256 as POOL_POLICY_SHA256
            from p04m_stock_registry import SCHEMA as POOL_SCHEMA, DEFINITION_SHA256
            aggregate = store.read_profile(args.account_id)
            result = dict(version=1, schema=POOL_SCHEMA, definition_sha256=DEFINITION_SHA256,
                registry_sha256=store.registry.sha256, policy_sha256=POOL_POLICY_SHA256, active=store.pool_active(),
                capabilities=store.registry.capabilities(aggregate))
        elif operation == "mixed-overview":
            if not args.mixed_ammo:raise TransactionError("P06T_ACTIVATION_REQUIRED")
            from p06t_mixed_store import POLICY_SHA256 as mixed_sha,SCHEMA as mixed_schema,SOURCE_SHA256
            aggregate=store.read_profile(args.account_id)
            result=dict(version=2,schema=mixed_schema,policy_sha256=mixed_sha,shell_catalog_sha256=SOURCE_SHA256,
                account_id=args.account_id,native_database_id=store._project_profile(args.account_id,aggregate)["native_database_id"],revision=aggregate["revision"],active=store.mixed_active())
        else:
            store.initialize()
            limit = request_limit(operation)
            raw = read_request(limit)
            request = json_value(raw, limit=limit, nodes=128 if args.owner_battle_hold and operation=="battle" else 64, depth=4)
            if operation=="hold-activate":
                from p08b_owner_hold_store import CONTRACT,POLICY_SHA256 as hold_sha
                from p09d_ammo_store import require
                require(args.owner_battle_hold and set(request)=={"version","contract","account_id","native_database_id","expected_revision","policy_sha256","old_sessions","pending_jobs","pending_returns"}
                    and type(request["version"])is int and request["version"]==5 and request["contract"]==CONTRACT and request["account_id"]==args.account_id and request["policy_sha256"]==hold_sha,"INVALID_INPUT")
                result=store.activate_hold(authenticated_account_id=args.account_id,native_database_id=request["native_database_id"],expected_revision=request["expected_revision"],
                    old_sessions=request["old_sessions"],pending_jobs=request["pending_jobs"],pending_returns=request["pending_returns"])
            elif operation=="loss-activate":
                from p06t_ammo_loss_store import AmmoLossStore,CONTRACT,POLICY_SHA256 as loss_sha
                from p09d_ammo_store import require
                require(args.ammo_rack_loss and isinstance(store,AmmoLossStore) and set(request)=={"version","contract","account_id","native_database_id","expected_revision","policy_sha256"}
                    and type(request["version"])is int and request["version"]==4 and request["contract"]==CONTRACT
                    and request["account_id"]==args.account_id and request["policy_sha256"]==loss_sha,"INVALID_INPUT")
                from p08b_battle_store import _integer
                _integer(request["native_database_id"],1);_integer(request["expected_revision"],13)
                result=store.activate_loss(account_id=args.account_id,authenticated_account_id=args.account_id,
                    expected_revision=request["expected_revision"],native_database_id=request["native_database_id"])
            elif operation=="mixed-activate":
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
            elif operation == "pool-activate": result = store.activate_pool(request, authenticated_account_id=args.account_id)
            elif operation == "battle": result = battle_service(store, request, authenticated_account_id=args.account_id)
            elif operation == "results":
                if args.owner_battle_hold:
                    from p08b_owner_hold_store import results_hold_service
                    result=results_hold_service(store,request,authenticated_account_id=args.account_id)
                elif args.ammo_rack_loss and request.get("version")==4:
                    from p06t_ammo_loss_store import results_loss_service
                    result=results_loss_service(store,request,authenticated_account_id=args.account_id)
                elif args.mixed_ammo and request.get("version")==2:
                    from p06t_mixed_store import results_service_mixed
                    result=results_service_mixed(store,request,authenticated_account_id=args.account_id)
                else:result = results_service(store, request, authenticated_account_id=args.account_id)
            elif operation == "research": result = native_service(store, request, authenticated_account_id=args.account_id)
            else: result = existing_service(store, operation, request, authenticated_account_id=args.account_id)
        return result

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("database", "bundle", "original-root", "account-id", "fixture-root"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--mixed-ammo",action="store_true",help="Explicit version2 owned mixed-ammunition worker")
    parser.add_argument("--owner-battle-hold",action="store_true",help="Explicit version5 held battle owner and all-method garage factory")
    parser.add_argument("--ammo-rack-loss",action="store_true",help="Explicit version4 owned ammo-rack loss accounting")
    parser.add_argument("--shell-catalog")
    parser.add_argument("--terminal-policy")
    parser.add_argument("--catalog-sha256",help="CAT-01: read admission identity from the single catalog with this exact hash (requires --mixed-ammo)")
    parser.add_argument("operation", choices=OPERATIONS)
    args = parser.parse_args()
    if args.mixed_ammo != bool(args.shell_catalog and args.terminal_policy) or (not args.mixed_ammo and (args.shell_catalog or args.terminal_policy)):
        parser.error("--mixed-ammo requires both trusted source files; source paths require the explicit opt-in")
    if args.ammo_rack_loss and not args.mixed_ammo:parser.error("--ammo-rack-loss requires --mixed-ammo and its trusted sources")
    if args.owner_battle_hold and not args.ammo_rack_loss:parser.error("--owner-battle-hold requires --ammo-rack-loss")
    if args.catalog_sha256 is not None:
        if not args.mixed_ammo:parser.error("--catalog-sha256 applies to the owned mixed worker only")
        import catalog_v1
        try:catalog_v1.activate(args.catalog_sha256)
        except catalog_v1.CatalogMismatch as error:parser.error("CAT-01 catalog refused: "+str(error))
    catalog = load_catalog(args.original_root)
    audit(args.original_root)
    context = WorkerContext(database=args.database, bundle=args.bundle, original_root=args.original_root,
        account_id=args.account_id, fixture_root=args.fixture_root, mixed_ammo=args.mixed_ammo,
        owner_battle_hold=args.owner_battle_hold, ammo_rack_loss=args.ammo_rack_loss,
        shell_catalog=args.shell_catalog, terminal_policy=args.terminal_policy, catalog=catalog)
    result = execute(context, args.operation, lambda limit: sys.stdin.buffer.read(limit + 1))
    print(canonical(result).decode("ascii"))

if __name__ == "__main__":
    try: main()
    except Exception as error:
        print(type(error).__name__ + ": " + str(error), file=sys.stderr)
        raise SystemExit(1)
