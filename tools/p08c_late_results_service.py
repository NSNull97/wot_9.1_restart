"""Trusted staged worker. Request data cannot choose paths, owner or mode."""
import argparse
import json
from pathlib import Path
import sys

# Active tools are trusted dependencies during staging; promotion removes this
# single bootstrap constant in favor of the normal repository-root bootstrap.
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from p08c_late_results import decode, service, pending_service, LateResultsStore, LossLateResultsStore, canonical
from p09e_research_catalog import load_catalog
from p09e_native_research_audit import audit
from p06t_ammo_loss_store import results_loss_service
from p06t_mixed_store import results_service_mixed


OPERATIONS = ("append", "results", "pending", "battle")
MAX_REQUEST = 65536


def run(args, operation, request):
    """One decoded late-owner request. ``args`` carries database, account_id,
    shell_catalog, terminal_policy, ammo_rack_loss and the loaded catalog."""
    cls = LossLateResultsStore if args.ammo_rack_loss else LateResultsStore
    with cls(args.database, args.catalog, account_id=args.account_id, shell_catalog=args.shell_catalog, terminal_policy=args.terminal_policy) as store:
        if not store.mixed_active(): raise ValueError("explicit existing mixed activation required")
        if args.ammo_rack_loss and not store.loss_active(): raise ValueError("explicit existing loss activation required")
        if operation == "battle":
            from p08b_battle_service import battle_service
            from p09d_ammo_store import require
            require(type(request) is dict and type(request.get("version")) is int
                and request["version"] == (4 if args.ammo_rack_loss else 2), "INVALID_INPUT")
            return battle_service(store, request, authenticated_account_id=args.account_id)
        if operation == "append":
            return service(store, request, authenticated_account_id=args.account_id)
        if operation == "pending":
            return pending_service(store, request, authenticated_account_id=args.account_id)
        method = results_loss_service if args.ammo_rack_loss else results_service_mixed
        return method(store, request, authenticated_account_id=args.account_id)


def execute(args, operation, raw):
    """Long-lived callers (DOM-01 Domain): raw request bytes, same decoder and bound."""
    return run(args, operation, decode(raw, MAX_REQUEST))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("database", "original-root", "account-id", "shell-catalog", "terminal-policy"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--ammo-rack-loss", action="store_true")
    parser.add_argument("operation", choices=OPERATIONS)
    args = parser.parse_args()
    raw = sys.stdin.buffer.read(MAX_REQUEST + 1)
    request = decode(raw, MAX_REQUEST)
    args.catalog = load_catalog(args.original_root); audit(args.original_root)
    value = run(args, args.operation, request)
    sys.stdout.buffer.write(canonical(value) + b"\n")


if __name__ == "__main__": main()
