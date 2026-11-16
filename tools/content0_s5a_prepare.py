"""Stage non-secret Domain support resources for an isolated 5a snapshot.

No service is started, and this does not make the stand ready for use.
Only source-local regular files are copied; any link, mutation, conflict,
resource limit or changed snapshot config causes a refusal.
"""
from pathlib import Path
import argparse
import hashlib
import json
import shutil
import sys
from tools.content0_s5a_stand import ROOT, no_link, read_stable, write_json, FREE_RESERVE

MAX_FILES = 10000
MAX_FILE = 128 * 1024 * 1024
MAX_BYTES = 512 * 1024 * 1024

def copy_tree(source, destination, boundary):
    source=Path(source).absolute();destination=Path(destination).absolute();boundary=Path(boundary).resolve(strict=True)
    no_link(source,boundary)
    if not source.is_dir() or destination.exists(): raise ValueError('source tree or fresh destination required')
    count=0;total=0; digest=hashlib.sha256()
    destination.mkdir(parents=True)
    for item in sorted(source.rglob('*')):
        no_link(item,boundary)
        if item.is_dir():continue
        if not item.is_file():raise ValueError('non-regular support resource')
        raw=read_stable(item,MAX_FILE);count+=1;total+=len(raw)
        if count>MAX_FILES or total>MAX_BYTES or shutil.disk_usage(destination).free < len(raw)+FREE_RESERVE:
            raise ValueError('support resource bounds')
        rel=item.relative_to(source);target=destination/rel;target.parent.mkdir(parents=True,exist_ok=True)
        with target.open('xb') as f:f.write(raw)
        digest.update(rel.as_posix().encode('utf-8'));digest.update(b'\0');digest.update(hashlib.sha256(raw).digest())
    return {'files':count,'bytes':total,'tree_sha256':digest.hexdigest()}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--stand',type=Path,required=True);a=p.parse_args()
    local=(ROOT/'local').resolve(strict=True);no_link(a.stand,local);stand=a.stand.resolve(strict=True)
    if not stand.is_relative_to(local/'stands'):raise ValueError('output stand outside checkout')
    receipt=json.loads(read_stable(stand/'snapshot-receipt.json'))
    if receipt['status']!='STAGED_NOT_READY' or Path(receipt['output']).resolve()!=stand:raise ValueError('not the staged snapshot')
    source=Path(receipt['source_stand']).resolve(strict=True);source_local=source.parent.parent
    raw=read_stable(source/'domain.json')
    if hashlib.sha256(raw).hexdigest()!=receipt['source_config_sha256']['domain.json']:raise ValueError('source Domain config changed after snapshot')
    config=json.loads(raw);roots={'bundle':Path(config['bundle']),'fixtures':Path(config['fixture_root'])}
    result={name:copy_tree(path,stand/'support'/name,source_local) for name,path in roots.items()}
    write_json(stand/'support-receipt.json',{'status':'STAGED_NOT_READY','resources':result})
    print(json.dumps({'status':'STAGED_NOT_READY','receipt':str(stand/'support-receipt.json')}))

if __name__=='__main__':
    try:main()
    except (OSError,ValueError,KeyError,json.JSONDecodeError) as e:
        print('support staging refused: '+type(e).__name__+': '+str(e),file=sys.stderr);raise SystemExit(1)
