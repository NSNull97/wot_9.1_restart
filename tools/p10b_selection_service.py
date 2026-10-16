"""Configured read-only worker for the distinct P10B selection contract."""
import argparse
import sys

from game_profile_tx import TransactionError
from p09e_research_catalog import load_catalog
from p08b_owner_source import projection_source
from p06t_mixed_store import MixedAmmoStore
from p10b_selection import SelectionReader,parse_request,MAX_REQUEST
from p09d_ammo_projection import canonical

DENIALS=frozenset(('INVALID_INPUT','STALE_REVISION','SOURCE_STAMP_MISMATCH','NATIVE_STATE_STAMP_MISMATCH',
    'RUN_NOT_OPEN','RUN_FENCED','VEHICLE_RESERVED','UNKNOWN_VEHICLE','BATTLE_PROFILE_UNSUPPORTED',
    'OWNER_ACCEPTANCE_REQUIRED','INCOMPLETE_CREW','AMMUNITION_EMPTY','AMMUNITION_UNSUPPORTED'))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in('database','bundle','original-root','account-id','shell-catalog','terminal-policy'):p.add_argument('--'+name,required=True)
    a=p.parse_args();request=parse_request(sys.stdin.buffer.read(MAX_REQUEST+1),a.account_id)
    catalog=load_catalog(a.original_root)
    source=projection_source(a.bundle,catalog,a.database,a.account_id)
    with MixedAmmoStore(a.database,catalog,account_id=a.account_id,shell_catalog=a.shell_catalog,terminal_policy=a.terminal_policy)as store:
        reply=SelectionReader(store,source).select(request,authenticated_account_id=a.account_id)
    sys.stdout.buffer.write(canonical(reply))


if __name__=='__main__':
    try:main()
    except TransactionError as error:
        if error.code in DENIALS:sys.stdout.buffer.write(canonical(dict(error='selection_not_ready',code=error.code)))
        else:print('selection_worker_unavailable',file=sys.stderr);raise SystemExit(1)
    except Exception:
        print('selection_worker_invalid_or_unavailable',file=sys.stderr);raise SystemExit(1)
