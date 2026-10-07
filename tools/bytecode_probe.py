"""Bounded static Python 2.7 inspection of configured client scripts; never executes them."""
import argparse
import re
from pathlib import Path
from client_audit import config, output_dir, read_limited, save_json, sha256
from py27_static import inspect, opcode_table


def run(args):
    _, paths = config()
    root = paths['research_client_root'] / 'res/scripts'
    table_path = paths['local_artifacts_root'] / 'vendor/cpython-2.7.18/opcode.py'
    table = opcode_table(table_path.read_text())
    pattern = re.compile(args.record) if args.record else None
    out = output_dir(args.out)
    index = []
    for name in args.module:
        if not re.fullmatch(r'(client|common)/[a-zA-Z0-9_/]{1,160}', name):
            raise ValueError('expected relative client/common module name without extension')
        path = root/(name+'.pyc')
        rows = inspect(read_limited(path, 16*1024*1024), table)
        if pattern:
            rows = [r for r in rows if pattern.search(r['qualified_name'])]
        dest = name.replace('/', '__')+'.json'
        save_json(out/dest, rows)
        index.append({'file': str(path), 'sha256': sha256(path), 'output': dest,
                      'records': [{'name': r['qualified_name'], 'line': r['firstlineno']} for r in rows]})
    save_json(out/'sources.json', {'modules': index, 'opcode_sha256': sha256(table_path), 'record_filter': args.record})
    for item in index:
        print({'file': item['file'], 'sha256': item['sha256'], 'selected_records': len(item['records'])})


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out', required=True)
    p.add_argument('--module', action='append', required=True)
    p.add_argument('--record')
    a = p.parse_args()
    if not 1 <= len(a.module) <= 16:
        p.error('1..16 modules per run')
    run(a)
