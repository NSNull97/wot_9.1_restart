"""Explicit, immutable relocation of historical crew/ammo evidence.

The sidecar describes locations, never a replacement native event or outcome.
Original export/plan/outcome/trace/probe bytes remain unchanged. Consumers still
run their complete producer, native-resource, event and process validation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import stat

from client_audit import config


KINDS = ('native-ms1-crew', 'native-ms1-ammo')
SUFFIX = '.relocation.json'
# Explicitly accepted export01 records. A different native run needs its own
# reviewed migration checkpoint; a sidecar cannot bless invented evidence.
CHECKPOINTS = {
    'native-ms1-crew': ('df0a9c26181a4efd65bfc8e9c34e2fbabc6f92a860db5676355890e400377a65',
                       '6f41620908c318964213e8a64ccad91cdcb9f7dc78bae267fe29a48470ebd41e'),
    'native-ms1-ammo': ('683daac81143a9d7edfbe671870ba163db088c54f5101fa52e077f596ebbfc74',
                       '263df3ff06a92458b4096627da2fd93b81d25e624d2eca283efbf37a2214e9a4'),
}
LIMITS = {'trace': 4 * 1024 * 1024, 'install_plan': 1024 * 1024,
          'outcome': 65536, 'compiled': 256 * 1024, 'metadata': 8192, 'bundle': 256 * 1024}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return (json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2) + '\n').encode('utf8')


def no_links(path):
    path = Path(path).absolute()
    require('..' not in path.parts, 'evidence parent traversal')
    for item in (path, *path.parents):
        try:
            info = item.lstat()
        except FileNotFoundError:
            continue
        require(not item.is_symlink() and not getattr(info, 'st_file_attributes', 0)
                & stat.FILE_ATTRIBUTE_REPARSE_POINT, 'linked evidence path')
    return path


def read(path, maximum):
    path = no_links(path)
    require(path.is_file() and 0 < path.stat().st_size <= maximum, 'evidence file bound')
    with path.open('rb') as stream:
        raw = stream.read(maximum + 1)
    require(0 < len(raw) <= maximum, 'evidence read bound')
    return raw


def parse(raw):
    def pairs(rows):
        require(len(rows) <= 128, 'evidence object bound')
        result = {}
        for key, value in rows:
            require(key not in result, 'duplicate evidence key')
            result[key] = value
        return result
    try:
        value = json.loads(raw, object_pairs_hook=pairs,
                           parse_constant=lambda _: require(False, 'nonfinite evidence'))
    except (RecursionError, UnicodeError) as error:
        raise ValueError('invalid evidence JSON') from error
    nodes = 0
    def visit(item, depth):
        nonlocal nodes
        nodes += 1
        require(depth <= 14 and nodes <= 8192, 'evidence structural bound')
        if type(item) is dict:
            for child in item.values():
                visit(child, depth + 1)
        elif type(item) is list:
            require(len(item) <= 256, 'evidence array bound')
            for child in item:
                visit(child, depth + 1)
        elif type(item) is str:
            require(len(item) <= 8192 and '\0' not in item, 'evidence string bound')
    visit(value, 0)
    return value


def local(path):
    _, paths = config()
    path = no_links(path)
    require(path.is_relative_to(paths['local_artifacts_root'])
            and path != paths['local_artifacts_root'], 'relocation must remain below local/')
    return path


def absolute(value):
    require(type(value) is str and 0 < len(value) <= 1024 and '\0' not in value,
            'historical evidence path bound')
    path = Path(value)
    require(path.is_absolute() and '..' not in path.parts, 'absolute historical evidence path required')
    return path


def relative(value):
    require(type(value) is str and 0 < len(value) <= 256 and not any(c in value for c in '\\:\0'),
            'canonical evidence relative path required')
    path = PurePosixPath(value)
    require(not path.is_absolute() and all(p not in ('', '.', '..') for p in path.parts)
            and str(path) == value, 'evidence relative path escape')
    return path


def layout(export, plan):
    """Derive the entire six-file closure from unchanged original evidence."""
    kind = export.get('kind')
    require(kind in KINDS, 'unsupported native export kind')
    proof = export['source']; prepared = absolute(proof['install_plan_file']).parent
    require(absolute(proof['install_plan_file']).name == 'install-plan.json'
            and absolute(proof['outcome_file']) == prepared / 'native-outcome.json', 'prepared run mismatch')
    module = kind.replace('native-', '').replace('-', '_') + '_probe'
    rows = [r for r in plan.get('sources', []) if type(r) is dict
            and r.get('path') == 'client_patch/' + module + '.py']
    require(len(rows) == 1, 'one native producer required')
    result = {}
    for name in ('trace', 'install_plan', 'outcome'):
        source = absolute(proof[name + '_file'])
        target = ('trace/' if name == 'trace' else 'prepared/') + source.name
        result[name] = (source, target)
    for name in ('compiled', 'metadata'):
        rel = relative(rows[0][name].replace('\\', '/'))
        result[name] = (prepared / str(rel), 'prepared/' + str(rel))
    rel = 'bundle/res_mods/0.9.1/scripts/client/' + module + '.pyc'
    result['bundle'] = (prepared / rel, 'prepared/' + rel)
    require(len({str(p) for p, _ in result.values()}) == 6, 'duplicate native evidence source')
    require(len({p for _, p in result.values()}) == 6, 'duplicate native evidence target')
    return result


class Relocation:
    def __init__(self, export_path, export_raw):
        self.export_path = local(export_path)
        sidecar = local(str(self.export_path) + SUFFIX)
        raw = read(sidecar, 16384); manifest = parse(raw)
        require(canonical(manifest) == raw, 'canonical relocation manifest required')
        require(type(manifest) is dict and set(manifest) == {
            'version', 'kind', 'export', 'source_roots', 'target_roots', 'files'}, 'relocation schema')
        require(type(manifest['version']) is int and manifest['version'] == 1
                and manifest['kind'] == 'native-evidence-relocation', 'relocation version/kind')
        export = parse(export_raw)
        require(export.get('kind') in CHECKPOINTS and digest(export_raw) == CHECKPOINTS[export['kind']][0],
                'unaccepted historical export checkpoint')
        require(manifest['export'] == {'file': self.export_path.name, 'bytes': len(export_raw),
                'sha256': digest(export_raw), 'kind': export['kind']}, 'relocation export binding changed')
        _, paths = config()
        require(manifest['target_roots'] == {key: str(paths[key + '_client_root'])
                for key in ('original', 'research')}, 'relocation target client roots changed')
        rows = manifest['files']
        require(type(rows) is list and len(rows) == 6, 'exact evidence closure required')
        self.files = {}
        for row in rows:
            require(type(row) is dict and set(row) == {'role', 'source', 'file', 'bytes', 'sha256'},
                    'relocation file schema')
            role = row['role']
            require(role in LIMITS and role not in self.files, 'duplicate/unknown evidence role')
            target = local(self.export_path.parent / str(relative(row['file'])))
            require(target.is_relative_to(self.export_path.parent) and target != self.export_path,
                    'relocation target escaped export directory')
            content = read(target, LIMITS[role])
            require(type(row['bytes']) is int and row['bytes'] == len(content)
                    and row['sha256'] == digest(content), 'relocated evidence bytes changed')
            self.files[role] = (absolute(row['source']), target, content)
        plan = parse(self.files['install_plan'][2]); expected = layout(export, plan)
        prefix = self.export_path.stem + '.relocated/'
        for row in rows:
            source, target = expected[row['role']]
            require(row['source'] == str(source) and row['file'] == prefix + target,
                    'relocation mapping differs from original closure')
        for role in ('trace', 'install_plan', 'outcome'):
            require(digest(self.files[role][2]) == export['source'][role + '_sha256'],
                    'relocation original proof hash changed')
        module = export['kind'].replace('native-', '').replace('-', '_') + '_probe'
        installed = [row for row in plan.get('files', []) if type(row) is dict
                     and row.get('path') == 'res_mods/0.9.1/scripts/client/' + module + '.pyc']
        require(len(installed) == 1 and digest(self.files['compiled'][2]) == digest(self.files['bundle'][2])
                == installed[0].get('installed_sha256')
                and digest(self.files['metadata'][2]) == CHECKPOINTS[export['kind']][1],
                'historical producer closure changed')
        require(manifest['source_roots'] == {key: str(absolute(plan[key + '_root']))
                for key in ('original', 'research')}, 'historical client root binding changed')
        self.manifest = manifest

    def proof_path(self, role, source):
        require(absolute(source) == self.files[role][0], 'unmapped historical proof')
        return self.files[role][1]

    def trace_root(self, source):
        require(absolute(source) == self.files['trace'][0].parent, 'historical trace root changed')
        return self.files['trace'][1].parent

    def client_roots(self, plan, paths, exe_sha):
        require(self.manifest['source_roots'] == {k: str(absolute(plan[k + '_root']))
                for k in ('original', 'research')}, 'historical roots differ')
        # Location is not build identity. Both configured copies must still be
        # the exact measured executable; original resource pins are checked by
        # the calling crew/ammo validator as before.
        for key in ('original', 'research'):
            require(digest(read(paths[key + '_client_root'] / 'WorldOfTanks.exe', 64 * 1024 * 1024))
                    == exe_sha, 'relocated client executable differs')


def for_export(path, raw):
    sidecar = no_links(str(Path(path).absolute()) + SUFFIX)
    return Relocation(path, raw) if sidecar.exists() else None


def import_export(source, source_root, destination):
    """Copy only the exact immutable proof closure; never edit historical bytes."""
    source_root = no_links(source_root).resolve(strict=True)
    source = no_links(source)
    require(source.is_relative_to(source_root) and source != source_root, 'export outside explicit source root')
    raw = read(source, 32768); export = parse(raw)
    require(export.get('kind') in CHECKPOINTS and digest(raw) == CHECKPOINTS[export['kind']][0],
            'unaccepted historical export checkpoint')
    plan_path = absolute(export['source']['install_plan_file'])
    require(plan_path.is_relative_to(source_root), 'prepared proof outside explicit source root')
    plan = parse(read(plan_path, LIMITS['install_plan']))
    destination = local(destination); _, paths = config()
    manifest = {'version': 1, 'kind': 'native-evidence-relocation',
                'export': {'file': destination.name, 'bytes': len(raw), 'sha256': digest(raw), 'kind': export['kind']},
                'source_roots': {k: str(absolute(plan[k + '_root'])) for k in ('original', 'research')},
                'target_roots': {k: str(paths[k + '_client_root']) for k in ('original', 'research')}, 'files': []}
    copies = [(destination, raw)]
    for role, (original, rel) in layout(export, plan).items():
        require(original.is_relative_to(source_root), 'proof outside explicit source root')
        content = read(original, LIMITS[role]); name = destination.stem + '.relocated/' + rel
        copies.append((local(destination.parent / name), content))
        manifest['files'].append({'role': role, 'source': str(original), 'file': name,
                                  'bytes': len(content), 'sha256': digest(content)})
    copies.append((local(str(destination) + SUFFIX), canonical(manifest)))
    # Preflight every collision before writing anything. No overwrite option.
    for path, content in copies:
        if path.exists():
            require(read(path, len(content)) == content, 'immutable import destination differs')
    for path, content in copies:
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            with path.open('xb') as stream:
                stream.write(content)
    # Full old producer/native-event validation remains the acceptance gate.
    if export['kind'] == 'native-ms1-crew':
        from ms1_crew_state import validate_export
    else:
        from ms1_ammo_state import validate_export
    validate_export(destination)
    return {'status': 'PASS', 'export': str(destination), 'export_sha256': digest(raw),
            'sidecar_sha256': digest(canonical(manifest)), 'copied_files': len(copies),
            'original_bytes_preserved': True}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(import_export(args.source, args.source_root, args.out), indent=2))
