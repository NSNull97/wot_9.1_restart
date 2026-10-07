"""Decode selected *real* local client data into ignored evidence, without execution."""
import argparse
import hashlib
from pathlib import Path
from client_audit import config, output_dir, read_limited, save_json, sha256
from packed_xml import decode, walk
from py27_static import inspect, opcode_table


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    _, paths = config()
    root = paths['research_client_root']
    out = output_dir(args.out)
    names = ['res/engine_config.xml', 'res/scripts_config.xml', 'res/scripts/entities.xml']
    names += [p.relative_to(root).as_posix() for p in sorted((root/'res/scripts/entity_defs').rglob('*')) if p.is_file()]
    names += ['res/scripts/item_defs/vehicles/'+name for name in [
        'ussr/t-34-85.xml', 'ussr/components/guns.xml', 'ussr/components/shells.xml',
        'germany/waffentrager_e100.xml', 'germany/components/guns.xml', 'germany/components/shells.xml',
        'uk/gb48_fv215b_183.xml', 'uk/components/guns.xml', 'uk/components/shells.xml']]
    source_index = []
    for name in names:
        path = root/name
        data = read_limited(path)
        tree = decode(data)
        dest = out/(name.replace('/', '__')+'.json')
        save_json(dest, tree)
        flat = list(walk(tree))
        save_json(dest.with_suffix('.flat.json'), flat)
        source_index.append({'path': name, 'sha256': sha256(path), 'bytes': len(data),
                             'output': dest.name, 'rows': len(flat)})
    op_path = paths['local_artifacts_root']/'vendor/cpython-2.7.18/opcode.py'
    table = opcode_table(op_path.read_text())
    pycs = ['game', 'connectionmanager', 'predefined_hosts', 'login', 'account', 'avatar',
            'vehicle', 'avatarpositioncontrol', 'clientarena', 'battlereplay']
    for module in pycs:
        name = 'res/scripts/client/'+module+'.pyc'
        path = root/name
        dest = out/(module+'.bytecode.json')
        save_json(dest, inspect(read_limited(path), table))
        source_index.append({'path': name, 'sha256': sha256(path), 'bytes': path.stat().st_size,
                             'output': dest.name})
    save_json(out/'sources.json', source_index)
    save_json(out/'opcode-source.json', {'path': str(op_path), 'sha256': sha256(op_path),
        'source_url': 'https://raw.githubusercontent.com/python/cpython/v2.7.18/Lib/opcode.py'})
    print(f'Decoded {len(source_index)} client files; source hashes in {out}/sources.json')


if __name__ == '__main__':
    main()
