"""Prepare an isolated 5a snapshot; never starts services or modifies the source.

This is a fail-closed staging tool, not a native acceptance or launch tool.
Source-local file paths and SHA pins are traversed and rewritten into the fresh
output; foreign references still require a separate audit before use. Missing
data, changed source files and cyclic manifests stop preparation. SQLite stores are backed up individually; no cross-database
atomic snapshot is claimed. Private files are never printed.
"""
from __future__ import annotations

import argparse
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import sqlite3
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
MAX_FILE = 128 * 1024 * 1024
MAX_FILES = 30_000
MAX_DEPTH = 32
MAX_TOTAL = 4 * 1024 * 1024 * 1024
FREE_RESERVE = 2 * 1024 * 1024 * 1024


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read_stable(path, limit=MAX_FILE):
    before = path.stat()
    if not path.is_file() or before.st_size > limit:
        raise ValueError('source file missing or exceeds bound')
    data = path.read_bytes()
    after = path.stat()
    if len(data) != before.st_size or (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise ValueError('source changed while reading')
    return data


def json_unique(raw):
    def pairs(rows):
        out = {}
        for key, value in rows:
            if key in out:
                raise ValueError('duplicate JSON field')
            out[key] = value
        return out
    return json.loads(raw.decode('utf-8-sig'), object_pairs_hook=pairs, parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite')))


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + '\n', encoding='utf-8')


def no_link(path, boundary):
    """Refuse junctions and symlinks between a path and its permitted root."""
    if '..' in Path(path).parts:
        raise ValueError('parent traversal refused')
    current = path.absolute()
    boundary = boundary.absolute()
    if not current.is_relative_to(boundary):
        raise ValueError('path outside permitted source root')
    while True:
        if current.is_symlink() or (hasattr(current, 'is_junction') and current.is_junction()):
            raise ValueError('linked resource refused')
        if current == boundary:
            break
        current = current.parent


def backup_database(source, target):
    # SQLite online backup includes committed WAL frames while the source is live.
    source = source.resolve(strict=True)
    with closing(sqlite3.connect(source.as_uri() + '?mode=ro', uri=True, timeout=10)) as src, closing(sqlite3.connect(target)) as dst:
        deadline = time.monotonic() + 120
        def progress(status, remaining, total):
            if time.monotonic() >= deadline:
                raise TimeoutError('SQLite online backup exceeded 120 seconds')
        src.backup(dst, pages=1024, sleep=0.01, progress=progress)
        quick = dst.execute('PRAGMA quick_check').fetchone()[0]
        integrity = dst.execute('PRAGMA integrity_check').fetchone()[0]
    if (quick, integrity) != ('ok', 'ok'):
        raise ValueError('snapshot database failed integrity check')
    return {'quick_check': quick, 'integrity_check': integrity, 'sha256': digest(target.read_bytes())}


def check_ports(ports):
    if len(set(ports.values())) != len(ports) or any(type(p) is not int or not 1024 <= p <= 65535 for p in ports.values()):
        raise ValueError('ports must be distinct nonprivileged integers')
    sockets = []
    try:
        for key, port in ports.items():
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM if key in ('login', 'base') else socket.SOCK_STREAM)
            sockets.append(sock)
            # Windows SO_EXCLUSIVEADDRUSE prevents a competing bind during the check.
            if hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            sock.bind(('127.0.0.1', port))
    finally:
        for sock in sockets:
            sock.close()


class Materializer:
    """Copy the transitive absolute/relative JSON file references, preserving pins."""
    def __init__(self, source_local, source_stand, dest, checkout):
        self.local, self.stand, self.dest, self.checkout = (Path(p).resolve(strict=True) for p in (source_local, source_stand, dest, checkout))
        if not self.stand.is_relative_to(self.local) or not self.dest.is_relative_to(self.checkout / 'local'):
            raise ValueError('invalid roots')
        self.done = {}
        self.active = set()
        self.bytes_written = 0
        self.terrain_provenance = []

    def destination(self, source):
        path = Path(source)
        if path.is_relative_to(self.stand):
            return self.dest / path.relative_to(self.stand)
        if path.is_relative_to(self.local):
            return self.dest / 'resources' / path.relative_to(self.local)
        raise ValueError('resource outside allowed local root')

    def file(self, source, expected=None, depth=0):
        source = Path(source).absolute()
        no_link(source, self.local)
        source = source.resolve(strict=True)
        if not source.is_relative_to(self.local) or depth > MAX_DEPTH:
            raise ValueError('foreign or too deep resource')
        if source in self.active:
            raise ValueError('cyclic source manifests')
        if source in self.done:
            target, source_sha, target_sha = self.done[source]
            if expected is not None and expected != source_sha:
                raise ValueError('source pin mismatch')
            return target, target_sha
        if len(self.done) >= MAX_FILES:
            raise ValueError('resource count bound')
        raw = read_stable(source)
        before_sha = digest(raw)
        if expected is not None and expected != before_sha:
            raise ValueError('source pin mismatch')
        self.active.add(source)
        try:
            target = self.destination(source)
            target.parent.mkdir(parents=True, exist_ok=True)
            if source.suffix.lower() == '.json':
                value = json_unique(raw)
                rewritten = self.value(value, source.parent, depth + 1)
                # Preserve exact bytes when no value changed; pins remain exact.
                output = raw if rewritten == value else (json.dumps(rewritten, indent=2, ensure_ascii=False, allow_nan=False) + '\n').encode('utf-8')
            else:
                output = raw
            if self.bytes_written + len(output) > MAX_TOTAL or shutil.disk_usage(self.dest).free < len(output) + FREE_RESERVE:
                raise ValueError('resource byte or free-space bound')
            target.write_bytes(output)
            self.bytes_written += len(output)
            output_sha = digest(output)
            self.done[source] = (target, before_sha, output_sha)
            return target, output_sha
        finally:
            self.active.remove(source)

    def value(self, value, parent, depth=0):
        if depth > MAX_DEPTH:
            raise ValueError('JSON depth bound')
        if isinstance(value, list):
            return [self.value(item, parent, depth + 1) for item in value]
        if not isinstance(value, dict):
            return value
        typed_mesh = isinstance(value.get('vertices'), dict) and isinstance(value.get('triangles'), dict)
        terrain = (typed_mesh and value.get('version') == 1 and value.get('kind') == 'original_091_static_triangle_mesh'
                   and value.get('vertices', {}).get('file') == 'terrain.vertices.f32'
                   and value.get('triangles', {}).get('file') == 'terrain.triangles.u32')
        obstacles = (typed_mesh and value.get('version') == 1 and value.get('kind') in ('original_091_projectile_static_triangle_mesh', 'original_091_static_triangle_mesh')
                     and value.get('vertices', {}).get('file') == 'obstacles.vertices.f32'
                     and value.get('triangles', {}).get('file') == 'obstacles.triangles.u32')
        # Terrain::load_for and Obstacles::load_for hard-pin manifest bytes and
        # explicitly never follow these provenance paths; preserve exact bytes.
        ignored = {'source'} if terrain else {'source_surface'} if obstacles else set()
        if ignored & value.keys():
            self.terrain_provenance.append(str(parent / 'manifest.json'))
        out = {key: item if key in ignored else self.value(item, parent, depth + 1)
               for key, item in value.items()}
        for key, item in value.items():
            if not isinstance(item, str):
                continue
            path = Path(item)
            # Only actual local files are resources; relative source metadata is
            # preserved unless it names a sibling with a pin.
            pin_name = 'sha256' if key in ('path', 'file') else key + '_sha256'
            expected = value.get(pin_name)
            if not path.is_absolute():
                if key not in ('path', 'file') or not isinstance(expected, str):
                    continue
                path = parent / path
                if not path.is_file():
                    continue
                # Crossings between separately mapped roots are unsafe.
                expected_target = (self.destination(parent) / Path(item)).resolve()
                if expected_target != self.destination(path.resolve()):
                    raise ValueError('relative pin crosses resource roots')
            if not path.is_relative_to(self.local):
                if path.is_absolute() and (str(path).lower().startswith(str(self.local).lower())):
                    raise ValueError('ambiguous resource path')
                continue
            if not path.is_file():
                raise ValueError(f'missing referenced local file: {path} (referenced from {parent})')
            target, new_sha = self.file(path, expected if isinstance(expected, str) else None, depth + 1)
            if Path(item).is_absolute():
                out[key] = str(target)
            if isinstance(expected, str):
                out[pin_name] = new_sha
        return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-stand', required=True, type=Path)
    parser.add_argument('--source-local', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--login-port', required=True, type=int)
    parser.add_argument('--base-port', required=True, type=int)
    parser.add_argument('--bridge-port', required=True, type=int)
    parser.add_argument('--domain-port', required=True, type=int)
    parser.add_argument('--guard-port', required=True, type=int)
    args = parser.parse_args()
    ports = dict(login=args.login_port, base=args.base_port, bridge=args.bridge_port, domain=args.domain_port, guard=args.guard_port)
    source_local = args.source_local.resolve(strict=True)
    no_link(args.source_stand, source_local)
    source = args.source_stand.resolve(strict=True)
    if not source.is_dir() or not source.is_relative_to(source_local / 'stands'):
        raise ValueError('source stand must be under the explicit source local/stands')
    local = (ROOT / 'local').resolve(strict=True)
    no_link(args.out, local)
    out = args.out.resolve()
    if not out.is_relative_to(local / 'stands') or out.exists():
        raise ValueError('fresh output below this checkout local/stands required')
    check_ports(ports)
    before = {name: read_stable(source / name) for name in ('bridge.json', 'gateway.json', 'domain.json', 'battle-profiles.json')}
    out.mkdir(parents=True)
    # The resource graph needs an existing destination. Failures deliberately
    # retain the partial evidence rather than deleting an unknown path.
    mat = Materializer(source_local, source, out, ROOT)
    databases = {name: backup_database(source / name, out / name) for name in ('game.sqlite', 'web.sqlite')}
    profiles = mat.value(json_unique(before['battle-profiles.json']), source)
    write_json(out / 'battle-profiles.json', profiles)
    for name in before:
        if read_stable(source / name) != before[name]:
            raise ValueError('source configuration changed during snapshot')
    receipt = {'schema':'content0-s5a-snapshot.v1', 'status':'STAGED_NOT_READY', 'native':'NOT_RUN',
        'source_stand':str(source), 'output':str(out), 'ports':ports, 'databases':databases,
        'source_config_sha256':{name:digest(raw) for name,raw in before.items()},
        'resource_files':len(mat.done), 'unfollowed_terrain_provenance':mat.terrain_provenance, 'cross_database_atomic':False,
        'remaining':['bind and validate bridge/domain/gateway configurations','new secrets and test credentials',
                     'verify complete resource closure and build identity','start own services in Domain-gateway-bridge order']}
    write_json(out / 'snapshot-receipt.json', receipt)
    print(json.dumps({'status':receipt['status'], 'receipt':str(out / 'snapshot-receipt.json'), 'resource_files':len(mat.done)}))


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, sqlite3.Error, json.JSONDecodeError) as error:
        print(f'content0-s5a snapshot refused: {type(error).__name__}: {error}', file=sys.stderr)
        raise SystemExit(1)
