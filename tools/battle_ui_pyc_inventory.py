"""Read-only inventory of Python 2.7 code records; never imports client code."""
import argparse
import hashlib
import json
from pathlib import Path

from py27_static import parse_pyc, records, text

MAX_SIZE = 16 * 1024 * 1024
MAX_RECORDS = 20000


def inspect(path):
    path = Path(path)
    if not path.is_file() or path.stat().st_size > MAX_SIZE:
        raise ValueError('expected a file of at most 16 MiB')
    with path.open('rb') as source:
        data = source.read(MAX_SIZE + 1)
    if len(data) > MAX_SIZE:
        raise ValueError('file grew beyond 16 MiB')
    root = parse_pyc(data)
    result = []
    for name, code in records(root):
        if len(result) >= MAX_RECORDS:
            raise ValueError('too many code records')
        result.append({'name': name, 'line': code['firstlineno'],
                       'names': text(code['names'])})
    return {'path': str(path), 'sha256': hashlib.sha256(data).hexdigest(),
            'records': result}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('path', type=Path)
    parser.add_argument('--contains', default='', help='filter record names and referenced names')
    args = parser.parse_args()
    result = inspect(args.path)
    if args.contains:
        query = args.contains.casefold()
        result['records'] = [r for r in result['records'] if query in
                             (r['name'] + ' ' + ' '.join(r['names'])).casefold()]
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
