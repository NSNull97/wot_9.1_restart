"""VISUAL-03: install/rollback only the owner-approved three DDS overrides.

The CLI is intentionally pinned to one local client and one manifest. It never
terminates a running process or overwrites an existing override. Files are
staged beside their targets, linked without replacement, and tracked by receipt.
"""
from __future__ import annotations

import argparse
import errno
import hashlib
import json
import os
import re
import subprocess
import sys
import uuid
import zipfile
from pathlib import Path, PurePosixPath
from xml.etree import ElementTree

from tools.destructible_catalog import no_links
from tools.visual02_dds import inspect_dds
from tools.visual02_paths import safe_evidence_output

CLIENT = Path('D:/WoT_9.1_Server/local/clients/content0-scoped-24')
PROFILE = Path('D:/WoT_9.1_Server/local/stands/content0-native-client-24/profile-a')
EVIDENCE_ROOT = Path('D:/WoT_9.1_Server/local/evidence')
MANIFEST = EVIDENCE_ROOT / 'visual03-batch-20261114/manifest.json'
PATHS_SHA256 = '9ae9340d5e78ef97225defd93e7c36eb8b26e6a3450015ed34c3c8f1a59668a3'
ARCHIVE = 'res/packages/vehicles_russian.pkg'
MAX_DDS = 128 * 1024 * 1024
MAX_MANIFEST = 1024 * 1024
ASSETS = {
    'vehicles/russian/R11_MS-1/MS-1.dds': {
        'source_sha256': 'd418c63aa7891034dbf34a2c26191cc8fc012cc385880811251ca12fda9d94c3',
        'format': 'DXT1', 'width': 2048, 'height': 1024, 'source_mips': 8,
        'output': 'out/MS-1.dds'},
    'vehicles/russian/tracks/MS-1_track.dds': {
        'source_sha256': '755f040c3a09ed2298dad38b01c0da8da5a359239689d7f6eae0feda1cef22ac',
        'format': 'DXT3', 'width': 256, 'height': 256, 'source_mips': 9,
        'output': 'out/MS-1_track.dds'},
    'vehicles/russian/tracks/SU-14_track.dds': {
        'source_sha256': '25647b5f88ad718b5568f97006f8c18fcb4d6233b532277788358ee12bc12a0d',
        'format': 'DXT5', 'width': 256, 'height': 256, 'source_mips': 9,
        'output': 'out/SU-14_track.dds'},
}


class InstallError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise InstallError(message)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def safe_read(path, limit):
    path = no_links(path)
    require(path.is_file(), 'missing regular file: ' + str(path))
    require(0 <= path.stat().st_size <= limit, 'file exceeds bound: ' + str(path))
    with path.open('rb') as stream:
        raw = stream.read(limit + 1)
    require(len(raw) <= limit, 'file grew beyond bound: ' + str(path))
    return raw


def evidence_path(path):
    return safe_evidence_output(path, root=EVIDENCE_ROOT)


def client_path(relative):
    require(relative in ASSETS, 'unknown client resource')
    root = no_links(CLIENT).resolve(strict=True)
    target = no_links(root / 'res_mods' / '0.9.1' / PurePosixPath(relative))
    resolved = target.resolve(strict=False)
    parent = (root / 'res_mods' / '0.9.1').resolve(strict=True)
    require(resolved.is_relative_to(parent), 'target escapes authorized override directory')
    return resolved


def _process_paths():
    """Fail closed when Windows process enumeration is unavailable/ambiguous."""
    command = ("$ErrorActionPreference='Stop'; "
               "$items=@(Get-CimInstance Win32_Process -Filter \"Name='WorldOfTanks.exe'\" "
               "| ForEach-Object { if (-not $_.ExecutablePath) { throw 'process path unavailable' }; "
               "[string]$_.ExecutablePath }); "
               "[Console]::OutputEncoding=[System.Text.Encoding]::UTF8; "
               "ConvertTo-Json -InputObject $items -Compress")
    done = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', command],
                          capture_output=True, timeout=20, check=True,
                          creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    result = json.loads(done.stdout.decode('utf-8-sig'))
    require(isinstance(result, list) and all(isinstance(x, str) and x for x in result),
            'invalid process enumeration')
    return result


def ensure_client_stopped():
    target = os.path.normcase(os.path.normpath(str(CLIENT / 'WorldOfTanks.exe')))
    require(not any(os.path.normcase(os.path.normpath(p)) == target for p in _process_paths()),
            'target client is running')


def read_manifest():
    manifest_path = evidence_path(MANIFEST)
    raw = safe_read(manifest_path, MAX_MANIFEST)
    doc = json.loads(raw.decode('utf-8-sig'))
    require(isinstance(doc, dict) and doc.get('schema') == 'wot091-visual03-batch.v1',
            'wrong manifest schema')
    rows = doc.get('assets')
    require(isinstance(rows, list) and len(rows) == len(ASSETS), 'manifest asset count')
    assets = {}
    for item in rows:
        require(isinstance(item, dict), 'manifest asset is not an object')
        name = item.get('resource')
        require(name in ASSETS and name not in assets, 'unknown or duplicate manifest resource')
        pin = ASSETS[name]
        require(item.get('source_sha256') == pin['source_sha256'], 'source hash pin mismatch: ' + name)
        require(item.get('source_mips') == pin['source_mips'] and
                item.get('output_mips') == pin['source_mips'] + 1, 'mip policy mismatch: ' + name)
        output = item.get('output')
        require(output == pin['output'] and isinstance(output, str), 'unexpected candidate path: ' + name)
        rel = PurePosixPath(output)
        require(not rel.is_absolute() and '..' not in rel.parts and '\\' not in output and ':' not in output,
                'unsafe candidate path')
        candidate = evidence_path(manifest_path.parent / rel)
        require(candidate.is_relative_to(manifest_path.parent), 'candidate escapes manifest folder')
        expected = item.get('output_sha256')
        require(isinstance(expected, str) and re.fullmatch(r'[0-9a-f]{64}', expected), 'invalid output hash')
        assets[name] = {'candidate': candidate, 'output_sha256': expected}
    require(set(assets) == set(ASSETS), 'manifest resources mismatch')
    return manifest_path, digest(raw), assets


def inspect_paths_and_sources():
    root = no_links(CLIENT).resolve(strict=True)
    profile = no_links(PROFILE).resolve(strict=True)
    raw = safe_read(root / 'paths.xml', MAX_MANIFEST)
    require(digest(raw) == PATHS_SHA256 and b'<!' not in raw, 'paths.xml pin mismatch')
    doc = ElementTree.fromstring(raw)
    values = [(n.text or '').strip() for n in doc.findall('./Paths/Path')]
    require(len(values) >= 3 and os.path.normcase(os.path.normpath(values[0])) ==
            os.path.normcase(os.path.normpath(str(profile))) and values[1] == './res_mods/0.9.1',
            'unexpected paths.xml precedence')
    packages = []
    for value in values[2:]:
        if value.lower().endswith('.pkg'):
            require(value.startswith('./res/packages/') and '..' not in PurePosixPath(value[2:]).parts,
                    'unsafe archive path')
            packages.append(value[2:])
    require(len(packages) <= 128 and packages.count(ARCHIVE) == 1, 'archive list invalid')
    # Ensure no earlier package shadows any target; loose high-priority profile
    # and res_mods are checked separately for each exact target.
    entries_seen = 0
    for rel in packages[:packages.index(ARCHIVE)]:
        p = no_links(root / rel)
        with zipfile.ZipFile(p) as archive:
            infos = archive.infolist()
            entries_seen += len(infos)
            require(entries_seen <= 1000000, 'ZIP entry count bound')
            names = {x.filename.casefold() for x in infos if not x.is_dir()}
            require(not (names & {x.casefold() for x in ASSETS}), 'earlier package shadows a resource: ' + rel)
    target_package = no_links(root / ARCHIVE)
    originals = {}
    with zipfile.ZipFile(target_package) as archive:
        infos = archive.infolist()
        entries_seen += len(infos)
        require(entries_seen <= 1000000, 'ZIP entry count bound')
        for name, pin in ASSETS.items():
            matches = [x for x in infos if not x.is_dir() and x.filename.casefold() == name.casefold()]
            require(len(matches) == 1 and matches[0].filename == name, 'archive resource missing or ambiguous: ' + name)
            info = matches[0]
            require(0 < info.file_size <= MAX_DDS and
                    info.file_size <= max(1024, info.compress_size * 2000), 'archive resource bound')
            data = archive.read(info)
            require(len(data) == info.file_size and digest(data) == pin['source_sha256'], 'source hash mismatch: ' + name)
            originals[name] = data
    for name in ASSETS:
        higher = no_links(profile / PurePosixPath(name))
        require(not higher.exists(), 'higher-priority profile override exists: ' + name)
        require(not client_path(name).exists(), 'target override already exists: ' + name)
    return originals


def validate_candidate(name, original, candidate):
    from tools.visual03_mips import alpha_plane
    pin = ASSETS[name]
    source_info, out_info = inspect_dds(original), inspect_dds(candidate)
    expected_source = (pin['format'], pin['width'], pin['height'], pin['source_mips'])
    require((source_info['format'], source_info['width'], source_info['height'], source_info['mip_count']) == expected_source,
            'unexpected original DDS structure: ' + name)
    require((out_info['format'], out_info['width'], out_info['height'], out_info['mip_count']) ==
            (pin['format'], pin['width'] * 2, pin['height'] * 2, pin['source_mips'] + 1),
            'unexpected candidate DDS structure: ' + name)
    require(source_info['trailing_bytes'] == out_info['trailing_bytes'] == 0, 'unexpected DDS trailing bytes')
    require(candidate[128 + out_info['mip_sizes'][0]:] == original[128:],
            'original mip chain changed: ' + name)
    if pin['format'] == 'DXT1':
        require(source_info['alpha_values_top_mip'] == [255] and out_info['alpha_values_top_mip'] == [255],
                'DXT1 alpha changed: ' + name)
    else:
        src, dst = alpha_plane(original), alpha_plane(candidate)
        w, h = pin['width'], pin['height']
        require(len(src) == w * h and len(dst) == (w * 2) * (h * 2), 'invalid alpha plane')
        for y in range(h):
            row = b''.join(bytes((value, value)) for value in src[y*w:(y+1)*w])
            start = y * 2 * w * 2
            require(dst[start:start + w*2] == row and dst[start+w*2:start+w*4] == row,
                    'top alpha is not exact 2x nearest: ' + name)


def write_receipt(path, data, *, first=False):
    path = evidence_path(path)
    payload = (json.dumps(data, sort_keys=True, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
    if first:
        with path.open('xb') as f:
            f.write(payload); f.flush(); os.fsync(f.fileno())
        return
    tmp = evidence_path(path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp'))
    owned = False
    try:
        with tmp.open('xb') as f:
            owned = True
            f.write(payload); f.flush(); os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        if owned and tmp.exists():
            tmp.unlink()


def acquire_lock(action, receipt_path, run):
    """A durable lock remains on process death and requires manual audit."""
    lock = evidence_path(MANIFEST.parent / 'visual03-operation.lock')
    content = json.dumps({'schema': 'wot091-visual03-lock.v1', 'id': run,
                          'action': action, 'receipt': str(receipt_path)}, sort_keys=True).encode('utf-8')
    try:
        with lock.open('xb') as f:
            identity = (os.fstat(f.fileno()).st_dev, os.fstat(f.fileno()).st_ino)
            f.write(content); f.flush(); os.fsync(f.fileno())
    except FileExistsError as exc:
        try:
            existing = safe_read(lock, MAX_MANIFEST).decode('utf-8', errors='replace')
        except Exception as read_error:
            existing = 'unreadable lock: ' + str(read_error)
        raise InstallError('unfinished or active operation; inspect lock ' + str(lock) + ': ' + existing) from exc
    return lock, identity


def release_lock(lock, identity, run):
    no_links(lock)
    require(_identity(lock) == identity, 'operation lock identity changed')
    value = json.loads(safe_read(lock, MAX_MANIFEST).decode('utf-8'))
    require(value.get('schema') == 'wot091-visual03-lock.v1' and value.get('id') == run,
            'operation lock content changed')
    lock.unlink()


def check_unfinished_receipts():
    """Unknown or unfinished receipts block a new operation; never auto-delete."""
    folder = evidence_path(MANIFEST).parent
    for path in folder.iterdir():
        if not re.fullmatch(r'(?:install|rollback)-[0-9a-f]{32}\.json', path.name):
            continue
        try:
            data = json.loads(safe_read(evidence_path(path), MAX_MANIFEST).decode('utf-8'))
            require(isinstance(data, dict) and data.get('schema') in
                    ('wot091-visual03-install-receipt.v1', 'wot091-visual03-rollback-receipt.v1'),
                    'unknown receipt schema')
            require(data.get('status') in ('PASS', 'FAIL_ROLLED_BACK', 'FAIL_NO_CHANGE'),
                    'unfinished or incomplete receipt')
        except Exception as exc:
            raise InstallError('inspect unfinished or invalid receipt ' + str(path) + ': ' + str(exc)) from exc


def finish_failure(receipt_path, receipt, lock, lock_id, run, exc, problems, incomplete, complete):
    receipt['status'] = incomplete if problems else complete
    receipt['errors'] = [str(exc)] + problems
    try:
        write_receipt(receipt_path, receipt)
        if not problems:
            try:
                release_lock(lock, lock_id, run)
            except Exception as lock_error:
                receipt['status'] = incomplete
                receipt['errors'].append('lock cleanup failed: ' + str(lock_error))
                write_receipt(receipt_path, receipt)
    except BaseException as receipt_error:
        if isinstance(receipt_error, (KeyboardInterrupt, SystemExit)):
            receipt_error.add_note('Receipt/lock update interrupted; inspect ' + str(receipt_path))
            raise
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            exc.add_note('Receipt/lock update failed; inspect ' + str(receipt_path) + ': ' + str(receipt_error))
            raise exc from receipt_error
        raise InstallError('operation failed and receipt/lock update failed; inspect ' +
                           str(receipt_path) + ': ' + str(receipt_error)) from exc
    if isinstance(exc, (KeyboardInterrupt, SystemExit)):
        exc.add_note('VISUAL-03 receipt: ' + str(receipt_path))
        raise exc
    raise InstallError('operation failed; receipt: ' + str(receipt_path) + '; ' + str(exc)) from exc


def make_dirs(path, stop, created):
    missing = []
    current = path
    while current != stop and not current.exists():
        missing.append(current); current = current.parent
    require(current == stop or current.is_relative_to(stop), 'directory escapes target root')
    for directory in reversed(missing):
        no_links(directory)
        record = {'path': directory, 'identity': None}
        created.append(record)
        try:
            directory.mkdir()
            record['identity'] = _identity(directory)
        except FileExistsError:
            require(directory.is_dir(), 'target parent is not directory')
            created.remove(record)
        no_links(directory)


def _identity(path):
    st = path.stat()
    return st.st_dev, st.st_ino


def install():
    run = uuid.uuid4().hex
    receipt_path = evidence_path(MANIFEST.parent / ('install-' + run + '.json'))
    receipt = {'schema': 'wot091-visual03-install-receipt.v1', 'id': run,
               'status': 'PREFLIGHT', 'manifest': str(MANIFEST), 'assets': [], 'errors': []}
    lock, lock_id = acquire_lock('install', receipt_path, run)
    try:
        check_unfinished_receipts()
    except BaseException:
        release_lock(lock, lock_id, run)
        raise
    write_receipt(receipt_path, receipt, first=True)
    plan, dirs = [], []
    try:
        ensure_client_stopped()
        _, manifest_sha, entries = read_manifest()
        originals = inspect_paths_and_sources()
        candidates = {}
        for name in ASSETS:
            data = safe_read(entries[name]['candidate'], MAX_DDS)
            require(digest(data) == entries[name]['output_sha256'], 'candidate hash mismatch: ' + name)
            validate_candidate(name, originals[name], data)
            candidates[name] = data
        receipt['manifest_sha256'] = manifest_sha
        for name in ASSETS:
            target = client_path(name)
            stage = no_links(target.with_name(target.name + '.visual03-' + run + '.tmp'))
            plan.append({'resource': name, 'target': target, 'stage': stage,
                         'identity': None, 'sha256': entries[name]['output_sha256']})
        receipt['assets'] = [{'resource': row['resource'], 'output_sha256': row['sha256'],
                              'target': str(row['target']), 'stage': str(row['stage']),
                              'stage_identity': None} for row in plan]
        receipt['status'] = 'PREPARED'
        write_receipt(receipt_path, receipt)
        ensure_client_stopped()
        stop = no_links(CLIENT / 'res_mods' / '0.9.1').resolve(strict=True)
        for row in plan:
            make_dirs(row['target'].parent, stop, dirs)
            with row['stage'].open('xb') as f:
                st = os.fstat(f.fileno())
                row['identity'] = (st.st_dev, st.st_ino)
                f.write(candidates[row['resource']]); f.flush(); os.fsync(f.fileno())
            require(digest(safe_read(row['stage'], MAX_DDS)) == row['sha256'], 'staging hash mismatch')
        for saved, row in zip(receipt['assets'], plan):
            saved['stage_identity'] = list(row['identity'])
        write_receipt(receipt_path, receipt)
        ensure_client_stopped()
        # Exclusive hardlink creation is atomic and refuses any existing target.
        for row in plan:
            ensure_client_stopped()
            require(client_path(row['resource']) == row['target'] and _identity(row['stage']) == row['identity'],
                    'target or staging identity changed')
            os.link(row['stage'], row['target'])
        for row in plan:
            require(_identity(row['target']) == row['identity'] and digest(safe_read(row['target'], MAX_DDS)) == row['sha256'],
                    'installed file identity/hash mismatch')
        for row in plan:
            require(_identity(row['stage']) == row['identity'], 'staging file identity changed before cleanup')
            row['stage'].unlink()
        receipt['status'] = 'PASS'
        write_receipt(receipt_path, receipt)
        release_lock(lock, lock_id, run)
        return receipt_path
    except BaseException as exc:
        problems, retained_dirs = [], []
        for row in reversed(plan):
            try:
                target = no_links(row['target'])
                if target.exists():
                    require(row['identity'] is not None and _identity(target) == row['identity'] and
                            digest(safe_read(target, MAX_DDS)) == row['sha256'],
                            'refuse to delete modified/non-owned target')
                    target.unlink()
            except Exception as cleanup:
                problems.append(str(cleanup))
        for row in plan:
            try:
                stage = no_links(row['stage'])
                if stage.exists():
                    require(row['identity'] is not None and _identity(stage) == row['identity'],
                            'refuse to delete non-owned staging file')
                    stage.unlink()
            except Exception as cleanup:
                problems.append(str(cleanup))
        for row in reversed(dirs):
            try:
                directory = no_links(row['path'])
                if not directory.exists():
                    continue
                require(row['identity'] is not None and _identity(directory) == row['identity'],
                        'refuse to delete non-owned directory: ' + str(directory))
                directory.rmdir()
            except InstallError as cleanup:
                problems.append(str(cleanup))
            except OSError as cleanup:
                if cleanup.errno in (errno.ENOTEMPTY, errno.EEXIST) or getattr(cleanup, 'winerror', None) in (145, 183):
                    retained_dirs.append(str(directory))
                else:
                    problems.append('directory cleanup failed: ' + str(cleanup))
        receipt['retained_nonempty_directories'] = retained_dirs
        finish_failure(receipt_path, receipt, lock, lock_id, run, exc, problems,
                       'FAIL_CLEANUP_INCOMPLETE', 'FAIL_ROLLED_BACK')


def rollback(install_receipt):
    run = uuid.uuid4().hex
    rollback_path = evidence_path(MANIFEST.parent / ('rollback-' + run + '.json'))
    receipt = {'schema': 'wot091-visual03-rollback-receipt.v1', 'id': run,
               'status': 'PREFLIGHT', 'install_receipt': str(install_receipt), 'assets': [], 'errors': []}
    lock, lock_id = acquire_lock('rollback', rollback_path, run)
    try:
        check_unfinished_receipts()
    except BaseException:
        release_lock(lock, lock_id, run)
        raise
    write_receipt(rollback_path, receipt, first=True)
    plan = []
    try:
        ensure_client_stopped()
        installation = json.loads(safe_read(evidence_path(install_receipt), MAX_MANIFEST).decode('utf-8'))
        require(installation.get('schema') == 'wot091-visual03-install-receipt.v1' and
                installation.get('status') == 'PASS', 'installation receipt is not PASS')
        _, manifest_sha, entries = read_manifest()
        require(installation.get('manifest_sha256') == manifest_sha, 'manifest changed since install')
        rows = installation.get('assets')
        require(isinstance(rows, list) and len(rows) == len(ASSETS), 'invalid installation receipt assets')
        by_name = {x.get('resource'): x for x in rows if isinstance(x, dict)}
        require(set(by_name) == set(ASSETS) and len(by_name) == len(rows), 'installation receipt resource mismatch')
        original_ids = {}
        for name in ASSETS:
            target = client_path(name)
            row = by_name[name]
            require(row.get('target') == str(target) and row.get('output_sha256') == entries[name]['output_sha256'],
                    'installation receipt content mismatch: ' + name)
            identity = _identity(target)
            expected_identity = row.get('stage_identity')
            require(isinstance(expected_identity, list) and len(expected_identity) == 2 and
                    all(type(x) is int for x in expected_identity) and identity == tuple(expected_identity),
                    'installed file identity changed; refusing rollback: ' + name)
            require(digest(safe_read(target, MAX_DDS)) == entries[name]['output_sha256'],
                    'installed file modified; refusing rollback: ' + name)
            require(_identity(target) == identity, 'installed file identity changed during preflight: ' + name)
            original_ids[name] = identity
        backup_dir = evidence_path(MANIFEST.parent / ('rollback-backup-' + run))
        backup_dir.mkdir()
        for i, name in enumerate(ASSETS):
            plan.append({'resource': name, 'source': client_path(name),
                         'backup': evidence_path(backup_dir / (str(i) + '-' + Path(name).name)),
                         'identity': original_ids[name], 'sha256': entries[name]['output_sha256']})
        receipt['assets'] = [{'resource': row['resource'], 'target': str(row['source']),
                              'backup': str(row['backup']), 'source_identity': list(row['identity']),
                              'output_sha256': row['sha256']} for row in plan]
        receipt['status'] = 'PREPARED'
        write_receipt(rollback_path, receipt)
        ensure_client_stopped()
        # Rename into local evidence retains every file and allows restoration on failure.
        for row in plan:
            ensure_client_stopped()
            source = client_path(row['resource']); backup = evidence_path(row['backup'])
            require(source == row['source'] and _identity(source) == row['identity'] and
                    digest(safe_read(source, MAX_DDS)) == row['sha256'], 'rollback source changed')
            require(not backup.exists(), 'rollback backup already exists')
            os.rename(source, backup)
        for row in plan:
            require(_identity(row['backup']) == row['identity'] and
                    digest(safe_read(row['backup'], MAX_DDS)) == row['sha256'], 'rollback backup hash mismatch')
        receipt['status'] = 'PASS'
        write_receipt(rollback_path, receipt)
        release_lock(lock, lock_id, run)
        return rollback_path
    except BaseException as exc:
        problems = []
        for row in reversed(plan):
            try:
                source, backup = no_links(row['source']), evidence_path(row['backup'])
                if backup.exists():
                    require(not source.exists() and _identity(backup) == row['identity'] and
                            digest(safe_read(backup, MAX_DDS)) == row['sha256'],
                            'cannot safely restore moved file')
                    os.rename(backup, source)
                    require(_identity(source) == row['identity'], 'restored source identity changed')
                else:
                    require(source.exists() and _identity(source) == row['identity'] and
                            digest(safe_read(source, MAX_DDS)) == row['sha256'],
                            'rollback source missing or changed')
            except Exception as restore:
                problems.append(str(restore))
        finish_failure(rollback_path, receipt, lock, lock_id, run, exc, problems,
                       'FAIL_RESTORE_INCOMPLETE', 'FAIL_NO_CHANGE')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    sub.add_parser('install')
    undo = sub.add_parser('rollback')
    undo.add_argument('--receipt', required=True, type=Path)
    args = parser.parse_args()
    try:
        result = install() if args.action == 'install' else rollback(args.receipt)
    except (InstallError, OSError, ValueError, subprocess.SubprocessError) as exc:
        print('FAIL:', exc, file=sys.stderr)
        return 1
    print('PASS', args.action, result)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
