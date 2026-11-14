"""Prepare a distinct, reversible #717 thin overlay; never launch the client.

This is not a research-copy manifest. Its resource source is the explicitly
investigated E: client and must be protected by a verified low token at launch.
"""
from __future__ import annotations
import argparse
import ast
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from client_audit import config, read_limited, sha256
from destructible_catalog import no_links
from shared_client_copy import ORIGINAL_EXE, patched_exe, checked_namespace

MARKER = 'content0_s5a_overlay.json'
SOURCE = Path('E:/WoT091_Content0_S5Crew_Client/local/clients/content0-step5-equipment-b')
MUTABLE = frozenset(('paths.xml', 'version.xml', 'res/engine_config.xml',
                     'res/text/LC_MESSAGES/menu.mo', 'res/text/LC_MESSAGES/system_messages.mo'))
MAX_MARKER = 4 * 1024 * 1024
SCHEMA = 'content0-s5a-thin-overlay.v1'


def canonical_original_relative(path, original):
    relative=path.relative_to(original).as_posix()
    prefix='res/text/lc_messages/'
    if relative.lower().startswith(prefix):
        return 'res/text/LC_MESSAGES/'+relative[len(prefix):]
    return relative


def parse_paths(raw):
    if not raw or len(raw)>65536: raise ValueError('bounded source paths required')
    tree=ET.fromstring(raw); paths=tree.find('Paths')
    if paths is None or len(tree)!=1 or any(node.tag!='Path' or len(node) for node in paths):
        raise ValueError('unexpected paths schema')
    values=[node.text for node in paths]
    if len(values)!=65 or values[0]!='./res_mods/0.9.1' or values[-2:]!=['./res','./res_bw']:
        raise ValueError('unexpected #717 search order')
    packages=values[1:-2]
    if (len(packages)!=62 or len(set(packages))!=62 or
            any(not isinstance(v,str) or not re.fullmatch(r'\./res/packages/[a-z0-9_]+\.pkg',v) for v in packages)):
        raise ValueError('unexpected #717 package list')
    return packages


def build_paths(raw, root, source):
    packages=parse_paths(raw)
    root,source=Path(root),Path(source)
    values=[root/'profile',root/'res_mods/0.9.1']+[source/p[2:] for p in packages]+[root/'res',source/'res',source/'res_bw']
    tree=ET.Element('root');paths=ET.SubElement(tree,'Paths')
    for path in values: ET.SubElement(paths,'Path').text=path.as_posix()
    return ET.tostring(tree,encoding='utf-8',xml_declaration=True)


def safe_root(value,paths,exists=True):
    local=no_links(paths['local_artifacts_root']).resolve(strict=True)
    clients=no_links(local/'clients').resolve(strict=False)
    root=no_links(value).resolve(strict=exists)
    if root==clients or not root.is_relative_to(clients):raise ValueError('overlay must be below local/clients')
    if exists and not root.is_dir():raise ValueError('overlay directory required')
    return root


def _unique(pairs):
    result={}
    for k,v in pairs:
        if k in result:raise ValueError('duplicate manifest field')
        result[k]=v
    return result


def checked_overlay(value, paths):
    root=safe_root(value,paths); marker=no_links(root/MARKER).resolve(strict=True)
    data=json.loads(read_limited(marker,MAX_MARKER),object_pairs_hook=_unique)
    keys={'schema','root','source','original_root','namespace','slot','instance_mutex','exe_sha256',
          'package_sha256','loose_sha256','immutable','baseline','native','paths_contract'}
    if type(data)!=dict or set(data)!=keys or data['schema']!=SCHEMA or data['native']!='NOT_RUN':
        raise ValueError('overlay manifest schema')
    original=no_links(paths['original_client_root']).resolve(strict=True)
    source=no_links(SOURCE).resolve(strict=True)
    if Path(data['root'])!=root or Path(data['source'])!=source or Path(data['original_root'])!=original:
        raise ValueError('overlay root/source identity changed')
    namespace=checked_namespace(data['namespace']);slot=data['slot']
    expected,edits=patched_exe(read_limited(original/'WorldOfTanks.exe'),slot,namespace)
    if (data['instance_mutex']!=edits[0]['after'] or data['exe_sha256']!=hashlib.sha256(expected).hexdigest()
            or sha256(no_links(root/'WorldOfTanks.exe'))!=data['exe_sha256']):
        raise ValueError('overlay EXE/mutex changed')
    if data['paths_contract']!='profile-resmods-e-packages-owned-res-e-res-e-resbw':
        raise ValueError('overlay paths contract changed')
    packages=parse_paths(read_limited(original/'paths.xml',65536))
    if type(data['package_sha256'])!=dict or set(data['package_sha256'])!=set(packages):
        raise ValueError('overlay package pin set')
    if any(not re.fullmatch(r'[0-9a-f]{64}',v) for v in data['package_sha256'].values()):
        raise ValueError('overlay package hash')
    if (type(data['loose_sha256'])!=dict or not 1<=len(data['loose_sha256'])<=10000
            or any(not isinstance(k,str) or not (k.startswith('res/') or k.startswith('res_bw/'))
                   or '\\' in k or '..' in Path(k).parts or not isinstance(v,str)
                   or not re.fullmatch(r'[0-9a-f]{64}',v) for k,v in data['loose_sha256'].items())):
        raise ValueError('overlay loose source inventory')
    if type(data['immutable'])!=dict or type(data['baseline'])!=dict or set(data['baseline'])!=MUTABLE:
        raise ValueError('overlay asset manifest')
    expected_immutable={'WorldOfTanks.exe','app_type.xml','res/scripts_config.xml'}
    expected_immutable.update(p.name for p in original.glob('*.dll'))
    expected_immutable.update(canonical_original_relative(p,original) for p in (original/'res/text').rglob('*') if p.is_file()
                              and canonical_original_relative(p,original) not in MUTABLE)
    if set(data['immutable'])!=expected_immutable: raise ValueError('overlay immutable inventory changed')
    for relative,expected_hash in data['immutable'].items():
        file=no_links(root/relative).resolve(strict=True)
        if not file.is_relative_to(root) or not re.fullmatch(r'[0-9a-f]{64}',expected_hash) or sha256(file)!=expected_hash:
            raise ValueError('overlay immutable file changed: '+relative)
        if relative!='WorldOfTanks.exe' and sha256(no_links(original/relative))!=expected_hash:
            raise ValueError('overlay immutable does not match original: '+relative)
    expected_baseline={p:sha256(no_links(original/p)) for p in MUTABLE if p!='paths.xml'}
    expected_baseline['paths.xml']=hashlib.sha256(build_paths(read_limited(original/'paths.xml',65536),root,source)).hexdigest()
    if data['baseline']!=expected_baseline:raise ValueError('overlay baseline changed')
    return root,data


def loose_files(source):
    """Bounded no-link traversal; packages are pinned separately."""
    found={};total=0
    for folder in ('res','res_bw'):
        base=no_links(source/folder).resolve(strict=True)
        if not base.is_relative_to(source) or not base.is_dir():raise ValueError('source directory missing')
        for current,dirs,files in os.walk(base,followlinks=False):
            for name in dirs:
                no_links(Path(current)/name)
            for name in files:
                path=no_links(Path(current)/name).resolve(strict=True)
                if not path.is_relative_to(source) or not path.is_file():raise ValueError('invalid loose source')
                relative=path.relative_to(source).as_posix()
                if relative.startswith('res/packages/') and relative.endswith('.pkg'):continue
                total+=path.stat().st_size
                if len(found)>=10000 or total>2*1024**3:raise ValueError('loose source bound')
                found[relative]=sha256(path)
    return found


def verify_source(data):
    """Full hash check; caller repeats immediately before each low-token run."""
    source=no_links(SOURCE).resolve(strict=True)
    expected_names={Path(p).name for p in data['package_sha256']}
    if {p.name for p in (source/'res/packages').glob('*.pkg')}!=expected_names:
        raise ValueError('source package set changed')
    for relative,expected in data['package_sha256'].items():
        path=no_links(source/relative[2:]).resolve(strict=True)
        if not path.is_relative_to(source) or sha256(path)!=expected:
            raise ValueError('source package changed: '+relative)
    if loose_files(source)!=data['loose_sha256']:raise ValueError('loose source changed')


def source_audit_pins():
    """Extract the existing native audit contracts without executing client code."""
    def literals(name,fields):
        path=Path(__file__).resolve().parents[1]/'client_patch'/name
        tree=ast.parse(path.read_text(encoding='utf-8'))
        result={}
        for item in tree.body:
            if isinstance(item,ast.Assign) and len(item.targets)==1 and isinstance(item.targets[0],ast.Name):
                key=item.targets[0].id
                if key in fields:
                    if key in result:raise ValueError('duplicate audit constant')
                    result[key]=ast.literal_eval(item.value)
        if set(result)!=set(fields):raise ValueError('native audit constants missing')
        return result
    battle=literals('hangar_capabilities.py',('BATTLE_SOURCE','BATTLE_PYC_SHA256'))
    drive=literals('map_drive_client.py',('LIGHT_SOURCE','LIGHT_SHA256','CAPTCHA_SOURCE','CAPTCHA_SHA256',
                                          'CAPTCHA_CHAIN_SOURCES','TRAINING_CHAIN_SOURCES'))
    arena=literals('arena_bootstrap.py',('SOURCE_HASHES',))
    pairs=[(battle['BATTLE_SOURCE'],battle['BATTLE_PYC_SHA256']),
           (drive['LIGHT_SOURCE'],drive['LIGHT_SHA256']),
           (drive['CAPTCHA_SOURCE'],drive['CAPTCHA_SHA256'])]
    pairs.extend(drive['CAPTCHA_CHAIN_SOURCES']);pairs.extend(drive['TRAINING_CHAIN_SOURCES'])
    pairs=[('res/'+name[:-3]+'.pyc',digest) for name,digest in pairs]
    pairs.extend(arena['SOURCE_HASHES'])
    result={}
    for name,digest in pairs:
        key=name.lower()
        if key in result and result[key]!=digest:raise ValueError('conflicting native audit pins')
        result[key]=digest
    return result


def script_payloads(original,source_pins,audit_pins=None):
    """Copy only the 14.6 MiB scripts tree, pinned against the audited E source.

    A complete scripts directory preserves directory-resolution behaviour; the
    runtime's existing audit checks remain intact and see actual local files.
    """
    original=no_links(original).resolve(strict=True);base=no_links(original/'res/scripts').resolve(strict=True)
    pins={}
    for name,digest in source_pins.items():
        key=name.lower()
        if key in pins:raise ValueError('ambiguous case in source inventory')
        pins[key]=digest
    payloads={};total=0
    def fail(error):raise error
    for current,dirs,files in os.walk(base,followlinks=False,onerror=fail):
        for name in dirs:no_links(Path(current)/name)
        for name in files:
            item=no_links(Path(current)/name).resolve(strict=True)
            if not item.is_relative_to(base) or not item.is_file():raise ValueError('invalid original script')
            relative=item.relative_to(original).as_posix();key=relative.lower()
            if key in (k.lower() for k in payloads):raise ValueError('ambiguous original script case')
            raw=read_limited(item,1024*1024);total+=len(raw)
            if len(payloads)>=4096 or total>128*1024*1024:raise ValueError('original scripts bound')
            if hashlib.sha256(raw).hexdigest()!=pins.get(key):raise ValueError('script differs from verified E source: '+relative)
            payloads[relative]=raw
    if {k for k in pins if k.startswith('res/scripts/')}!={k.lower() for k in payloads}:
        raise ValueError('original and verified E script inventory differ')
    checks=source_audit_pins() if audit_pins is None else audit_pins
    for name,expected in checks.items():
        item=no_links(original/name).resolve(strict=True)
        if not item.is_relative_to(original) or sha256(item)!=expected:
            raise ValueError('native source audit pin mismatch: '+name)
    return payloads,{'files':len(payloads),'bytes':total,'native_audit_pins':len(checks),
                     'source':'original and verified E SHA-256','native':'NOT_RUN'}


def create(args):
    _,paths=config();root=safe_root(args.root,paths,False)
    if root.exists():raise ValueError('fresh overlay root required')
    original=no_links(paths['original_client_root']).resolve(strict=True)
    source=no_links(SOURCE).resolve(strict=True)
    if root.is_relative_to(source) or root.is_relative_to(original):raise ValueError('overlay source overlap')
    raw=read_limited(original/'WorldOfTanks.exe');exe,edits=patched_exe(raw,args.slot,args.namespace)
    xml=read_limited(original/'paths.xml',65536);packages=parse_paths(xml)
    if {p.name for p in (source/'res/packages').glob('*.pkg')}!={Path(p).name for p in packages}:
        raise ValueError('E package set differs from original paths')
    package_hashes={}
    for relative in packages:
        src=no_links(source/relative[2:]).resolve(strict=True);reference=no_links(original/relative[2:]).resolve(strict=True)
        if not src.is_relative_to(source) or not reference.is_relative_to(original):raise ValueError('package escapes root')
        actual=sha256(src)
        if actual!=sha256(reference):raise ValueError('E package differs from original: '+relative)
        package_hashes[relative]=actual
    loose_hashes=loose_files(source)
    files=['app_type.xml','version.xml','res/scripts_config.xml','res/engine_config.xml']
    files += [p.name for p in sorted(original.glob('*.dll'))]
    text_root=no_links(original/'res/text').resolve(strict=True)
    for p in sorted(text_root.rglob('*')):
        no_links(p)
        if p.is_file():files.append(canonical_original_relative(p,original))
    if not MUTABLE-{'paths.xml'} <= set(files) or len(files)>1024:raise ValueError('baseline inventory invalid')
    root.mkdir(parents=True)
    from content0_s5a_configure import restrict_directory
    restrict_directory(root)
    subprocess.run(['icacls',str(root),'/setintegritylevel','(OI)(CI)L'],check=True,capture_output=True)
    immutable={};baseline={}
    for relative in files:
        src=no_links(original/relative).resolve(strict=True);dest=root/relative
        if not src.is_relative_to(original):raise ValueError('baseline escaped original')
        dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dest)
        (baseline if relative in MUTABLE else immutable)[relative]=sha256(dest)
    (root/'WorldOfTanks.exe').write_bytes(exe);immutable['WorldOfTanks.exe']=hashlib.sha256(exe).hexdigest()
    (root/'profile').mkdir();(root/'runtime').mkdir();(root/'res_mods/0.9.1').mkdir(parents=True)
    payload=build_paths(xml,root,source);(root/'paths.xml').write_bytes(payload)
    baseline['paths.xml']=hashlib.sha256(payload).hexdigest()
    data={'schema':SCHEMA,'root':str(root),'source':str(source),'original_root':str(original),'namespace':args.namespace,
          'slot':args.slot,'instance_mutex':edits[0]['after'],'exe_sha256':immutable['WorldOfTanks.exe'],
          'package_sha256':package_hashes,'loose_sha256':loose_hashes,'immutable':immutable,'baseline':baseline,'native':'NOT_RUN',
          'paths_contract':'profile-resmods-e-packages-owned-res-e-res-e-resbw'}
    with (root/MARKER).open('x',encoding='utf-8') as out:json.dump(data,out,sort_keys=True,indent=2);out.write('\n')
    checked_overlay(root,paths)
    print(json.dumps({'status':'THIN_OVERLAY_PREPARED','root':str(root),'manifest':str(root/MARKER),'native':'NOT_RUN'}))


def rollback_inventory(root,data):
    """Read-only preflight: refuse unknown or edited contents before deletion."""
    allowed={MARKER}|set(data['immutable'])|set(data['baseline'])
    actual=set();directories=set()
    for p in root.rglob('*'):
        no_links(p)
        if p.is_file():actual.add(p.relative_to(root).as_posix())
        elif p.is_dir():directories.add(p.relative_to(root).as_posix())
    if actual!=allowed:raise ValueError('unrecognized or missing overlay files; preserved')
    known_dirs={'profile','runtime','res_mods','res_mods/0.9.1'}
    for relative in allowed:
        parent=Path(relative).parent
        while parent!=Path('.'):
            known_dirs.add(parent.as_posix());parent=parent.parent
    if directories!=known_dirs:raise ValueError('unrecognized overlay directories; preserved')
    for relative,expected in data['baseline'].items():
        if sha256(no_links(root/relative))!=expected:raise ValueError('overlay patch rollback required: '+relative)
    return allowed,known_dirs


def rollback(args):
    _,paths=config();root,data=checked_overlay(args.root,paths)
    from instance_mutex import control
    with control(data['instance_mutex']):
        # The caller must roll back its own patch ledger first; user-created
        # profiles/logs and unknown directories are never deleted.
        allowed,known_dirs=rollback_inventory(root,data)
        for relative in sorted(allowed-{MARKER},key=lambda x:len(Path(x).parts),reverse=True):
            (root/relative).unlink()
        (root/MARKER).unlink()
        for relative in sorted(known_dirs,key=lambda x:len(Path(x).parts),reverse=True):
            (root/relative).rmdir()
        root.rmdir()
    print(json.dumps({'status':'THIN_OVERLAY_REMOVED'}))


def main():
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='op',required=True)
    prep=sub.add_parser('create');prep.add_argument('--root',required=True);prep.add_argument('--slot',choices=('a','b'),required=True)
    prep.add_argument('--namespace',required=True);prep.set_defaults(func=create)
    undo=sub.add_parser('rollback');undo.add_argument('--root',required=True);undo.set_defaults(func=rollback)
    args=parser.parse_args();args.func(args)


if __name__=='__main__':main()
