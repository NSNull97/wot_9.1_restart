"""Create an independent #717 local research copy with isolated instance names.

Only two fixed UTF-16 strings change in the EXE. No code branch, gameplay or
network byte is patched. All resources are copied, never hard-linked to original.
The manifest and original EXE remain beside the copy for reversible inspection.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

from client_audit import ROOT, config, read_limited, sha256

ORIGINAL_EXE = '86f5e351d44c12e0d2b89ed741ee9a4e70d21f234c39aa9cfd709536d49f04ed'
MARKER = 'sr_lab_copy.json'
STRINGS = ((20731348, 'wot_client_mutex'), (20731996, 'wot_wait_for_mutex'))
MARKER_FIELDS = {'version', 'scope', 'slot', 'root', 'original_root', 'original_exe_sha256',
                 'patched_exe_sha256', 'instance_mutex', 'patches', 'resource_copy_bytes',
                 'links_created', 'network_gameplay_code_modified', 'native_two_instances'}


def owned_copy(value, paths, must_exist=True):
    raw = ROOT / value
    root = raw.resolve()
    allowed = paths['local_artifacts_root'] / 'clients'
    if not root.is_relative_to(allowed) or root == allowed:
        raise ValueError('Additional clients must be strictly below local/clients/')
    for parent in (raw, *raw.parents):
        if parent.is_symlink() or (hasattr(parent, 'is_junction') and parent.is_junction()):
            raise ValueError('Linked client copy refused')
        if parent == ROOT:
            break
    if must_exist and not root.is_dir():
        raise ValueError('Research copy absent')
    return root


def checked_namespace(namespace):
    if (not isinstance(namespace, str) or len(namespace) != 4
            or any(c not in 'abcdefghijklmnopqrstuvwxyz0123456789' for c in namespace)):
        raise ValueError('Instance namespace must be exactly four lowercase ASCII letters/digits')
    return namespace


def patched_exe(raw, slot, namespace=None):
    if slot not in ('a', 'b') or hashlib.sha256(raw).hexdigest() != ORIGINAL_EXE:
        raise ValueError('Only the pinned original #717 EXE and lab slot a/b are supported')
    prefix = 'p03f' if namespace is None else checked_namespace(namespace)
    data = bytearray(raw)
    edits = []
    for (offset, old), name in zip(STRINGS, (f'sr_{prefix}_{slot}_mutex', f'sr_{prefix}_{slot}_wait')):
        name = name.ljust(len(old), '_')
        before = (old + '\0').encode('utf-16le')
        after = (name + '\0').encode('utf-16le')
        if len(before) != len(after) or raw[offset:offset + len(before)] != before or raw.count(before) != 1:
            raise ValueError('Pinned unique native mutex string mismatch')
        data[offset:offset + len(after)] = after
        edits.append({'offset': offset, 'before': old, 'after': name, 'bytes': len(after)})
    return bytes(data), edits


def checked_copy(value, paths):
    root = owned_copy(value, paths)
    marker = root / MARKER
    if marker.stat().st_size > 4096:
        raise ValueError('Research-copy manifest bound')
    def unique_fields(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError('Duplicate research-copy manifest field')
            value[key] = item
        return value
    data = json.loads(marker.read_text(encoding='utf-8'), object_pairs_hook=unique_fields)
    if (not isinstance(data, dict) or type(data.get('version')) is not int
            or data['version'] not in (1, 2)
            or set(data) != MARKER_FIELDS | ({'namespace'} if data['version'] == 2 else set())):
        raise ValueError('Research-copy manifest schema mismatch')
    namespace = checked_namespace(data['namespace']) if data['version'] == 2 else None
    if (any(not isinstance(data[key], str) for key in ('root', 'original_root', 'slot', 'native_two_instances'))
            or data.get('scope') != 'p03f-two-client-lab'
            or Path(data.get('root', '')) != root
            or Path(data.get('original_root', '')) != paths['original_client_root']
            or data.get('original_exe_sha256') != ORIGINAL_EXE
            or data.get('slot') not in ('a', 'b')
            or type(data['resource_copy_bytes']) is not int or data['resource_copy_bytes'] < 0
            or data['links_created'] is not False or data['network_gameplay_code_modified'] is not False):
        raise ValueError('Research-copy identity/hash mismatch')
    expected, edits = patched_exe(read_limited(root / 'WorldOfTanks.exe.p03f-backup'), data['slot'], namespace)
    expected_hash = hashlib.sha256(expected).hexdigest()
    if (not isinstance(data['patches'], list) or len(data['patches']) != 2
            or any(not isinstance(row, dict) or set(row) != {'offset', 'before', 'after', 'bytes'}
                   or type(row['offset']) is not int or type(row['bytes']) is not int for row in data['patches'])
            or data['patches'] != edits or data['instance_mutex'] != edits[0]['after']
            or data['patched_exe_sha256'] != expected_hash
            or sha256(root / 'WorldOfTanks.exe') != expected_hash):
        raise ValueError('Research-copy expected names/patches/hash mismatch')
    return root, data


def create(args):
    _, paths = config()
    root = owned_copy(args.root, paths, False)
    original = paths['original_client_root']
    if root.exists():
        raise ValueError('Fresh client-copy path required; partial copies are preserved')
    raw = (original / 'WorldOfTanks.exe').read_bytes()
    namespace = getattr(args, 'namespace', None)
    replacement, edits = patched_exe(raw, args.slot, namespace)
    entries = list(original.rglob('*'))
    if any(p.is_symlink() or (hasattr(p, 'is_junction') and p.is_junction()) for p in (original, *entries)):
        raise ValueError('Linked original resources refused')
    total = sum(p.stat().st_size for p in entries if p.is_file())
    if shutil.disk_usage(paths['local_artifacts_root']).free < total + 2 * 1024**3:
        raise ValueError('Insufficient space for a full independent copy')
    root.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(original, root, copy_function=shutil.copy2)
    copied = root / 'WorldOfTanks.exe'
    if sha256(copied) != ORIGINAL_EXE:
        raise ValueError('Copied EXE differs from original')
    shutil.copy2(copied, root / 'WorldOfTanks.exe.p03f-backup')
    copied.write_bytes(replacement)
    data = {'version': 1 if namespace is None else 2, 'scope': 'p03f-two-client-lab', 'slot': args.slot,
            'root': str(root), 'original_root': str(original), 'original_exe_sha256': ORIGINAL_EXE,
            'patched_exe_sha256': sha256(copied), 'instance_mutex': edits[0]['after'],
            'patches': edits, 'resource_copy_bytes': total, 'links_created': False,
            'network_gameplay_code_modified': False, 'native_two_instances': 'NOT_RUN'}
    if namespace is not None:
        data['namespace'] = namespace
    (root / MARKER).write_text(json.dumps(data, indent=2) + '\n', encoding='utf-8')
    checked_copy(root, paths)
    if sha256(original / 'WorldOfTanks.exe') != ORIGINAL_EXE:
        raise ValueError('Original EXE guard failed')
    print(json.dumps({'status': 'PREPARED_INDEPENDENT_RESEARCH_COPY', 'root': str(root),
                      'manifest': str(root / MARKER), 'bytes_copied': total}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', required=True)
    parser.add_argument('--slot', required=True, choices=('a', 'b'))
    parser.add_argument('--namespace', help='Exactly four lowercase ASCII letters/digits; omitted preserves v1 names')
    create(parser.parse_args())


if __name__ == '__main__':
    main()
