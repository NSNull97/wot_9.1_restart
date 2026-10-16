import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'tests/helpers'),str(ROOT/'tools'),str(ROOT)]
from p08b_owner_hold_fixture import *
def main():
 destination=Path(sys.argv[1]).resolve();part=destination.relative_to(ROOT/'local/web/tests');assert len(part.parts)==2 and part.parts[0].startswith('run-')and part.parts[1]=='game.sqlite'
 f=Fixture(database=destination,activate=False)
 try:
  f.activate(0);f.battle(0,'run_open')
  r=f.request(1,'run_open');r.update(version=4,contract=LOSS_CONTRACT);AmmoLossStore.battle_loss(f.stores[1],r,authenticated_account_id=f.accounts[1])
  data=dict(database=str(destination),bundle=f.seed['bundle'],original=f.seed['original'],profiles=[f.public(0),f.public(1)],run_id=f.run,source_database_sha256=f.seedsha,source_unchanged=True,new_grants=0)
  destination.with_suffix('.json').write_bytes(canonical(data));print('PREPARED_ACTUAL_HOLD5_C_LOSS4_D_NO_GRANTS')
 finally:f.close()
if __name__=='__main__':main()
