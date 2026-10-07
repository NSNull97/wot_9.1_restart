"""Check source ownership and keep generated/private artifacts out of server/."""
import argparse
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
ALLOWED_SUFFIXES = {'.py', '.mjs', '.rs', '.toml', '.lock', '.json', '.cs', '.csproj', '.md', '.ps1'}
GENERATED_DIRECTORIES = {'target', 'bin', 'obj', '__pycache__', 'node_modules'}
SECRET_NAMES = {'identity.token', 'project.local.json', 'service.json', 'gateway.json',
                'bridge.json', 'pool.json', '.env', 'state.json'}


def linked(path):
    return path.is_symlink() or (hasattr(path, 'is_junction') and path.is_junction())


def relative_path(value):
    if (not isinstance(value, str) or not value or '\\' in value or ':' in value
            or value.startswith('/') or any(part in ('', '.', '..') for part in value.split('/'))):
        raise ValueError('Unsafe relative layout path')
    return Path(value)


def check(root=ROOT):
    root = Path(root).resolve()
    server = root / 'server'
    if linked(server):
        raise ValueError('Linked server root')
    manifest = json.loads((server / 'layout.json').read_text(encoding='utf-8'))
    if manifest.get('version') != 1:
        raise ValueError('Unsupported layout manifest')
    files = []
    seen = set()
    for path in sorted(server.rglob('*')):
        rel = path.relative_to(server)
        if linked(path):
            raise ValueError(f'Linked server entry: {rel}')
        if path.is_dir():
            if path.name in GENERATED_DIRECTORIES:
                raise ValueError(f'Build/cache output in source directory: {rel}')
            continue
        if (not path.is_file() or path.suffix not in ALLOWED_SUFFIXES
                or path.name in SECRET_NAMES or path.name.startswith('.env')):
            raise ValueError(f'Private/generated/unexpected server file: {rel}')
        if re.search(r'(?i)(?:^p\d+[_-]|091|v\d+[_.-])', path.name):
            raise ValueError(f'Version/phase in canonical file name: {rel}')
        key = rel.as_posix().casefold()
        if key in seen:
            raise ValueError(f'Case collision: {rel}')
        seen.add(key)
        data = path.read_bytes()
        files.append({'path': 'server/' + rel.as_posix(), 'bytes': len(data),
                      'sha256': hashlib.sha256(data).hexdigest()})
    mapped = []
    destinations = set()
    for old, new in manifest['relocations'].items():
        source = root / relative_path(old)
        target = root / relative_path(new)
        if not target.is_relative_to(server) or not target.is_file():
            raise ValueError(f'Missing canonical source: {new}')
        if source.exists():
            raise ValueError(f'Duplicate editable source remains: {old}')
        if new.casefold() in destinations:
            raise ValueError('Duplicate canonical destination')
        destinations.add(new.casefold())
        mapped.append({'legacy': old, 'canonical': new})
    for value in manifest['legacy_entrypoints'] + manifest['frozen_shared_dependencies']:
        path = root / relative_path(value)
        if not path.is_file() or linked(path):
            raise ValueError(f'Missing/linked declared shared dependency: {value}')
    return {'status': 'PASS_SERVER_SOURCE_LAYOUT', 'server_files': files,
            'single_source_relocations': mapped,
            'shared_dependency_count': len(manifest['frozen_shared_dependencies']),
            'remote_or_linux_readiness': 'NOT_RUN; this is a source layout check'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', help='Fresh JSON receipt below project local/')
    args = parser.parse_args()
    result = check()
    if args.out:
        path = (ROOT / args.out).resolve()
        if not path.is_relative_to(ROOT / 'local'):
            raise ValueError('Receipt must remain below project local/')
        for ancestor in (path.parent, *path.parents):
            if ancestor == ROOT:
                break
            if linked(ancestor):
                raise ValueError('Linked receipt parent')
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('x', encoding='utf-8', newline='\n') as stream:
            json.dump(result, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
    print(json.dumps({'status': result['status'], 'source_files': len(result['server_files']),
                      'single_source_relocations': len(result['single_source_relocations']),
                      'remote_or_linux_readiness': result['remote_or_linux_readiness']}))


if __name__ == '__main__':
    main()
