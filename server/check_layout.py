"""Check source ownership and keep generated/private artifacts out of server/.

REFACTOR-01 R0 (2026-11-03): file names of every code area follow the rule of
docs/SOURCE_LAYOUT.md (a name says what the file does: no phase/card number, no
client version). Names that broke it before this check covered them are the
`name_debt` of server/layout.json; a new one fails, and an entry whose file no
longer breaks the rule fails too, so the list only shrinks. In a git checkout
an ignored cache or build directory under server/ is skipped; a tracked one fails.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
ALLOWED_SUFFIXES = {'.py', '.mjs', '.rs', '.toml', '.lock', '.json', '.cs', '.csproj', '.md', '.ps1'}
# Git attributes that pin source bytes (server/physics/Profiles).
ALLOWED_NAMES = {'.gitattributes'}
GENERATED_DIRECTORIES = {'target', 'bin', 'obj', '__pycache__', 'node_modules'}
SECRET_NAMES = {'identity.token', 'project.local.json', 'service.json', 'gateway.json',
                'bridge.json', 'pool.json', '.env', 'state.json'}
# Code areas whose file names follow the naming rule.
NAME_AREAS = ('server', 'tools', 'tests', 'client_patch', 'web/src', 'web/tests')
# A name token that is a card or phase ID (p06t, p04j, ui03, av01, bw01, net01...),
# a client version (091) or a schema version (v2). Vehicle names (ms1, is7, t34)
# are content, not phases.
CARD_TOKEN = re.compile(r'(?i)^(?:p\d{2}[a-z]?\d*|(?:av|bw|net|ui|arena|gw|mm|cat|dom|spawn|late|perf|crash|stab'
                        r'|turret|input|ft|load|pg|bot|res)\d{1,2}[a-z]?|v\d+|0?91)$')


def linked(path):
    return path.is_symlink() or (hasattr(path, 'is_junction') and path.is_junction())


def relative_path(value):
    if (not isinstance(value, str) or not value or '\\' in value or ':' in value
            or value.startswith('/') or any(part in ('', '.', '..') for part in value.split('/'))):
        raise ValueError('Unsafe relative layout path')
    return Path(value)


def name_breaks_rule(name):
    """True when a file name carries a card/phase number or a version."""
    stem = name.split('.', 1)[0]
    return '091' in stem or any(CARD_TOKEN.match(token) for token in re.split(r'[_.\-]', stem) if token)


def tracked_files(root):
    """Tracked paths (posix, relative) of a git checkout, or None outside git."""
    if not (root / '.git').exists():
        return None
    out = subprocess.run(['git', '-C', str(root), 'ls-files', '-z', '--', *NAME_AREAS],
                         capture_output=True, check=True).stdout
    return [item.decode('utf-8') for item in out.split(b'\0') if item]


def name_report(root, debt):
    """(new breaks, stale debt entries) of the naming rule over the code areas."""
    paths = tracked_files(root)
    if paths is None:
        paths = [path.relative_to(root).as_posix() for area in NAME_AREAS if (root / area).is_dir()
                 for path in (root / area).rglob('*') if path.is_file()]
    breaking = {path for path in paths if name_breaks_rule(path.rsplit('/', 1)[-1])}
    debt = set(debt)
    return sorted(breaking - debt), sorted(debt - breaking)


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
    tracked = tracked_files(root)
    tracked_server = None if tracked is None else {path for path in tracked if path.startswith('server/')}
    entries = []
    for directory, names, file_names in os.walk(server):
        directory = Path(directory)
        for name in list(names):
            path = directory / name
            rel = path.relative_to(server)
            if linked(path):
                raise ValueError(f'Linked server entry: {rel}')
            if name in GENERATED_DIRECTORIES:
                prefix = 'server/' + rel.as_posix() + '/'
                if tracked_server is None or any(item.startswith(prefix) for item in tracked_server):
                    raise ValueError(f'Build/cache output in source directory: {rel}')
                names.remove(name)
        entries += [directory / name for name in file_names]
    for path in sorted(entries):
        rel = path.relative_to(server)
        if linked(path):
            raise ValueError(f'Linked server entry: {rel}')
        if (not path.is_file() or (path.suffix not in ALLOWED_SUFFIXES and path.name not in ALLOWED_NAMES)
                or path.name in SECRET_NAMES or path.name.startswith('.env')):
            raise ValueError(f'Private/generated/unexpected server file: {rel}')
        if (re.search(r'(?i)(?:^p\d+[_-]|091|v\d+[_.-])', path.name)
                and 'server/' + rel.as_posix() not in manifest.get('name_debt', ())):
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
    new_names, stale_debt = name_report(root, manifest.get('name_debt', ()))
    if new_names:
        raise ValueError('Card/phase/version in file name: ' + ', '.join(new_names[:10]))
    if stale_debt:
        raise ValueError('Stale name_debt entry (the file is renamed or gone): ' + ', '.join(stale_debt[:10]))
    return {'status': 'PASS_SERVER_SOURCE_LAYOUT', 'server_files': files,
            'name_debt': len(manifest.get('name_debt', ())),
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
                      'name_debt': result['name_debt'],
                      'remote_or_linux_readiness': result['remote_or_linux_readiness']}))


if __name__ == '__main__':
    main()
