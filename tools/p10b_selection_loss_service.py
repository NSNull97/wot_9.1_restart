"""Configured read-only API4 selection worker; registration is explicit."""
import argparse
from pathlib import Path
import sys


def repository_root(script):
    """Closed trusted CLI layout: ordinary tools/ or ignored promotion candidate.

    No working-directory, environment, or caller-supplied root fallback. At most
    ten ancestors are inspected; both project sentinels must name actual files.
    """
    for root in tuple(script.resolve(strict=True).parents)[:10]:
        if (root / 'server/gateway/Cargo.toml').is_file() and (root / 'tools/p08b_battle_service.py').is_file():
            return root
    raise RuntimeError('selection_loss_repository_root_unavailable')


SCRIPT_DIRECTORY = Path(__file__).resolve(strict=True).parent
ROOT = repository_root(Path(__file__))
# The colocated versioned reader wins over the project dependency directory.
# This is also the ordinary production tools/ layout after promotion.
for directory in (ROOT, ROOT / 'tools', SCRIPT_DIRECTORY):
    value = str(directory)
    if value in sys.path:
        sys.path.remove(value)
    sys.path.insert(0, value)

from game_profile_tx import TransactionError
from p09e_research_catalog import load_catalog
from p08b_owner_source import projection_source
from p06t_ammo_loss_store import AmmoLossStore
from p10b_selection_loss import SelectionLossReader, parse_request, MAX_REQUEST
from p09d_ammo_projection import canonical

DENIALS = frozenset(('INVALID_INPUT', 'STALE_REVISION', 'SOURCE_STAMP_MISMATCH', 'NATIVE_STATE_STAMP_MISMATCH',
    'RUN_NOT_OPEN', 'RUN_FENCED', 'VEHICLE_RESERVED', 'UNKNOWN_VEHICLE', 'BATTLE_PROFILE_UNSUPPORTED',
    'OWNER_ACCEPTANCE_REQUIRED', 'INCOMPLETE_CREW', 'AMMUNITION_EMPTY', 'AMMUNITION_UNSUPPORTED',
    'AMMO_LOSS_POLICY_REQUIRED', 'OWNER_CONTRACT_UNSUPPORTED'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('database', 'bundle', 'original-root', 'account-id', 'shell-catalog', 'terminal-policy'):
        parser.add_argument('--' + name, required=True)
    args = parser.parse_args()
    request = parse_request(sys.stdin.buffer.read(MAX_REQUEST + 1), args.account_id)
    catalog = load_catalog(args.original_root)
    source = projection_source(args.bundle, catalog, args.database, args.account_id)
    with AmmoLossStore(args.database, catalog, account_id=args.account_id,
                       shell_catalog=args.shell_catalog, terminal_policy=args.terminal_policy) as store:
        reply = SelectionLossReader(store, source).select(request, authenticated_account_id=args.account_id)
    sys.stdout.buffer.write(canonical(reply))


if __name__ == '__main__':
    try:
        main()
    except TransactionError as error:
        if error.code in DENIALS:
            sys.stdout.buffer.write(canonical(dict(error='selection_not_ready', code=error.code)))
        else:
            print('selection_loss_worker_unavailable', file=sys.stderr)
            raise SystemExit(1)
    except Exception:
        print('selection_loss_worker_invalid_or_unavailable', file=sys.stderr)
        raise SystemExit(1)
