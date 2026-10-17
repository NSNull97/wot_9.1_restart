"""Fixture-only source-owned C/D setup. Selection itself never activates/publishes."""
from contextlib import closing
from pathlib import Path
import json, sqlite3, sys
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'tests'),str(ROOT/'tests/helpers'),str(ROOT/'tools'),str(ROOT)]
import p10b_selection_hold_support as s

def main():
    destination=s.plain(Path(sys.argv[1]))
    relative=destination.relative_to(ROOT/'local/web/tests')
    assert len(relative.parts)==2 and relative.parts[0].startswith('run-') and relative.parts[1]=='game.sqlite'
    assert destination.parent.is_dir() and not destination.exists()
    catalog=s.load_catalog(s.context_seed(1,s.ROOT)[0]['original'])
    fx=s.Fixture(1,catalog)
    try:
        profiles=[store._project_profile(a,store.read_profile(a)) for a,store in zip(fx.accounts,fx.stores)]
        with closing(sqlite3.connect(fx.database.as_uri()+'?mode=ro',uri=True)) as src,closing(sqlite3.connect(destination)) as out:
            src.execute('PRAGMA query_only=ON');src.execute('BEGIN');before=s.logical(src);src.backup(out)
            assert s.logical(out)==before;src.rollback()
        data=dict(schema='p10b-hold-selection-http-seed.v1',database=str(destination),bundle=fx.metadata['bundle'],original=fx.metadata['original'],profiles=profiles,run_id=s.RUN,
            source_before=fx.source_before,source_after=s.source_refs(fx.source),source_unchanged=True,new_grants=0,setup=s.SETUPS[-1],copied_logical_sha256=before)
        destination.with_suffix('.json').write_bytes(s.canonical(data))
        print('PREPARED_HOLD_SELECTION_C_D_NO_GRANTS')
    finally:fx.close()

if __name__=='__main__':main()
