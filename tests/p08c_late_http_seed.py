"""Fresh disposable actual SQL lineage for the staged exact adapter branch."""
from contextlib import closing
import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3
import sys

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('late_sql_tests', HERE / 'test_p08c_late_results.py')
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
destination = Path(sys.argv[1]).resolve()
relative = destination.relative_to(m.ROOT / 'local/web/tests')
if len(relative.parts) != 2 or not relative.parts[0].startswith('run-') or relative.parts[1] != 'game.sqlite' or destination.exists():
    raise ValueError('Fresh controlled test database required')
seed = json.loads(m.SEED.read_bytes()); original_sha = hashlib.sha256(Path(seed['database']).read_bytes()).hexdigest()
f = m.Scenario(m.load_catalog(seed['original']), True)
try:
    finals = [f.final(0), f.final(1)]; result = f.result(finals)
    f.finish(0, finals[0]); f.finish(1, finals[1], result)
    request = f.append_request(finals, result)
    profiles = [f.public(store) for store in f.stores]
    with closing(sqlite3.connect(destination)) as output: f.stores[0].connection.backup(output)
    metadata = dict(schema='p08c-late-http-actual-sql-seed.v1', database=str(destination), source_seed=str(m.SEED),
        source_database_sha256=original_sha, bundle=seed['bundle'], original=seed['original'], profiles=profiles,
        request=request, results_json=m.canonical(result).decode('utf8'),
        source_stand_writes=False, native='NOT_RUN', stats='AUTHORED_GATEWAY_FINAL_SNAPSHOT')
    with destination.with_suffix('.json').open('xb') as out: out.write(m.canonical(metadata))
    assert hashlib.sha256(Path(seed['database']).read_bytes()).hexdigest() == original_sha
    print('PREPARED_REAL_ISOLATED_SQL_SEED')
finally: f.close()
