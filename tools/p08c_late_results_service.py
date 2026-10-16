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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("database", "original-root", "account-id", "shell-catalog", "terminal-policy"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--ammo-rack-loss", action="store_true")
    parser.add_argument("operation", choices=("append", "results", "pending"))
    args = parser.parse_args()
    raw = sys.stdin.buffer.read(65537)
    request = decode(raw, 65536)
    catalog = load_catalog(args.original_root); audit(args.original_root)
    cls = LossLateResultsStore if args.ammo_rack_loss else LateResultsStore
    with cls(args.database, catalog, account_id=args.account_id, shell_catalog=args.shell_catalog, terminal_policy=args.terminal_policy) as store:
        if not store.mixed_active(): raise ValueError("explicit existing mixed activation required")
        if args.ammo_rack_loss and not store.loss_active(): raise ValueError("explicit existing loss activation required")
        if args.operation == "append":
            value = service(store, request, authenticated_account_id=args.account_id)
        elif args.operation == "pending":
            value = pending_service(store, request, authenticated_account_id=args.account_id)
        else:
            method = results_loss_service if args.ammo_rack_loss else results_service_mixed
            value = method(store, request, authenticated_account_id=args.account_id)
    sys.stdout.buffer.write(canonical(value) + b"\n")


if __name__ == "__main__": main()
