"""Read-only audit of explicitly configured WoT copies. Python 3.11+; stdlib only."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import struct
import sys
import time
import zipfile

ROOT = Path(__file__).resolve().parents[1]
MAX_FILE = 64 * 1024 * 1024


def sha256(path: Path) -> str:
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def config():
    data = json.loads((ROOT / 'config/project.local.json').read_text(encoding='utf-8-sig'))
    paths = {k: Path(v).resolve(strict=True) for k, v in data['paths'].items()}
    if paths['original_client_root'] == paths['research_client_root']:
        raise ValueError('original and research must differ')
    for key in ('original_client_root', 'research_client_root'):
        if paths[key].is_relative_to(paths['local_artifacts_root']):
            raise ValueError('client must not be inside output tree')
    return data, paths


def output_dir(value: str) -> Path:
    _, paths = config()
    target = (ROOT / value).resolve()
    if not target.is_relative_to(paths['local_artifacts_root']):
        raise ValueError('output must be inside configured local/')
    target.mkdir(parents=True, exist_ok=True)
    return target


def save_json(path: Path, data):
    # Evidence is append-only: reruns use another directory.
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2)
        stream.write('\n')


def read_limited(path: Path, maximum=MAX_FILE) -> bytes:
    if path.stat().st_size > maximum:
        raise ValueError(f'file too large: {path}')
    with path.open('rb') as stream:
        data = stream.read(maximum + 1)
    if len(data) > maximum:
        raise ValueError('file grew beyond limit')
    return data


def files(root: Path):
    for parent, dirs, names in os.walk(root, followlinks=False):
        dirs.sort()
        for name in dirs + names:
            path = Path(parent) / name
            if path.is_symlink() or (hasattr(path, 'is_junction') and path.is_junction()):
                raise ValueError(f'links/junctions forbidden in audit: {path}')
        for name in sorted(names):
            yield Path(parent) / name


def manifest(root: Path):
    result = []
    started = time.monotonic()
    last = started
    for path in files(root):
        before = path.stat()
        digest = sha256(path)
        after = path.stat()
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise ValueError(f'file changed while hashing: {path}')
        result.append({'path': path.relative_to(root).as_posix(), 'bytes': before.st_size,
                       'sha256': digest, 'mtime_ns': before.st_mtime_ns})
        if time.monotonic() - last > 20:
            print(f'{root.name}: hashed {len(result)} files', flush=True)
            last = time.monotonic()
    return {'root': str(root), 'files': result, 'file_count': len(result),
            'bytes': sum(x['bytes'] for x in result),
            'extensions': dict(Counter(Path(x['path']).suffix for x in result)),
            'elapsed_seconds': time.monotonic() - started}


def compare(a, b):
    left = {x['path']: (x['bytes'], x['sha256']) for x in a['files']}
    right = {x['path']: (x['bytes'], x['sha256']) for x in b['files']}
    return {'only_left': sorted(left.keys() - right.keys()),
            'only_right': sorted(right.keys() - left.keys()),
            'different': sorted(k for k in left.keys() & right.keys() if left[k] != right[k])}


def audit(args):
    cfg, paths = config()
    out = output_dir(args.out)
    save_json(out / 'environment.json', {'utc': datetime.now(timezone.utc).isoformat(),
        'python': sys.version, 'executable': sys.executable, 'platform': platform.platform(),
        'command': sys.argv, 'paths': {k: str(v) for k, v in paths.items()}})
    manifests = []
    for key, name in [('original_client_root', 'original'), ('research_client_root', 'research')]:
        item = manifest(paths[key])
        save_json(out / f'{name}-manifest.json', item)
        save_json(out / f'{name}-content-manifest.json', [
            {k: row[k] for k in ('path', 'bytes', 'sha256')} for row in item['files']])
        manifests.append(item)
    diff = compare(*manifests)
    save_json(out / 'copy-comparison.json', diff)
    print(json.dumps({'counts': [x['file_count'] for x in manifests], 'comparison': diff}))


def metadata(args):
    _, paths = config()
    root = paths['research_client_root']
    out = output_dir(args.out)
    keys = ['version.xml', 'paths.xml', 'app_type.xml', 'WorldOfTanks.exe',
            'res/engine_config.xml', 'res/scripts_config.xml', 'res/loginapp_wot.pubkey',
            'res/scripts/entities.xml', 'res/scripts/entity_defs/alias.xml',
            'res/scripts/client/game.pyc', 'res/scripts/client/connectionmanager.pyc']
    key_info = []
    for name in keys:
        path = root / name
        if path.is_file():
            data = read_limited(path)
            key_info.append({'path': name, 'bytes': len(data), 'sha256': sha256(path),
                             'first16_hex': data[:16].hex()})
        else:
            key_info.append({'path': name, 'status': 'ABSENT'})
    pycs = Counter()
    for path in files(root):
        if path.suffix.lower() == '.pyc':
            with path.open('rb') as stream:
                pycs[stream.read(4).hex()] += 1
    binary = read_limited(root / 'WorldOfTanks.exe')
    pe_offset = struct.unpack_from('<I', binary, 0x3c)[0]
    if binary[pe_offset:pe_offset+4] != b'PE\0\0':
        raise ValueError('not a PE executable')
    machine, sections, stamp = struct.unpack_from('<HHI', binary, pe_offset + 4)
    strings = [{'offset': m.start(), 'value': m.group().decode('ascii')}
               for m in re.finditer(rb'[\x20-\x7e]{6,}', binary)
               if re.search(rb'Python 2|2\.7\.[0-9]|MSC v\.|Jun 17 2014|BigWorld Release|--config|--script|--res', m.group())]
    save_json(out / 'metadata.json', {'keys': key_info, 'pyc_magics': dict(pycs),
        'pe': {'machine_hex': hex(machine), 'sections': sections, 'timestamp': stamp},
        'selected_exe_strings': strings,
        'version_xml': (root/'version.xml').read_text(),
        'resource_search_paths_xml': (root/'paths.xml').read_text()})
    packages = []
    for path in sorted((root / 'res/packages').glob('*.pkg')):
        with zipfile.ZipFile(path) as archive:
            entries = archive.infolist()
            if len(entries) > 300000:
                raise ValueError('too many package entries')
            info = [{'name': x.filename, 'size': x.file_size, 'compressed': x.compress_size,
                     'crc32': f'{x.CRC:08x}', 'compression': x.compress_type} for x in entries]
            save_json(out / (path.stem + '-index.json'), info)
            packages.append({'path': path.relative_to(root).as_posix(), 'count': len(info),
                             'bytes': path.stat().st_size})
    save_json(out/'packages.json', packages)
    print(json.dumps({'pyc_magics': dict(pycs), 'packages': len(packages), 'pe_machine': hex(machine)}))


def package_read(root: Path, relative: str, entry: str, maximum=MAX_FILE) -> bytes:
    path = (root / relative).resolve(strict=True)
    if not path.is_relative_to(root):
        raise ValueError('package escaped client root')
    with zipfile.ZipFile(path) as archive:
        info = archive.getinfo(entry)
        if info.file_size > maximum or info.compress_size == 0 and info.file_size:
            raise ValueError('package member too large/invalid')
        if info.file_size > max(info.compress_size, 1) * 1000:
            raise ValueError('compression ratio exceeds limit')
        with archive.open(info) as stream:
            data = stream.read(maximum+1)
        if len(data) != info.file_size or len(data) > maximum:
            raise ValueError('package size mismatch')
        return data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(required=True)
    for name, fn in [('manifest', audit), ('metadata', metadata)]:
        cmd = sub.add_parser(name)
        cmd.add_argument('--out', required=True, help='new evidence directory inside local/')
        cmd.set_defaults(run=fn)
    args = parser.parse_args()
    args.run(args)


if __name__ == '__main__':
    main()
