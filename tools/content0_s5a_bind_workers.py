"""Stage exact pinned Jolt pool runtime assets for an inactive isolated stand."""
import argparse,hashlib,json,sys
from pathlib import Path
from tools.content0_s5a_stand import ROOT,no_link,read_stable,write_json

def stage_runtime(source,dest,rows):
    source=Path(source).absolute();dest=Path(dest).absolute()
    if source.is_symlink() or (hasattr(source,'is_junction') and source.is_junction()) or dest.is_symlink() or (hasattr(dest,'is_junction') and dest.is_junction()):raise ValueError('linked runtime root')
    source=source.resolve(strict=True);dest=dest.resolve(strict=True)
    if not isinstance(rows,list) or not 1<=len(rows)<=256:raise ValueError('artifact list bounds')
    expected=set();total=0
    for row in rows:
        if not isinstance(row,dict) or set(row)!={'relative_path','bytes','sha256'}:raise ValueError('artifact row')
        text=row['relative_path']
        if not isinstance(text,str) or not text or '\\' in text or any(not part or part in ('.','..') or ':' in part for part in text.split('/')):raise ValueError('artifact path')
        rel=Path(text)
        if rel.is_absolute() or rel in expected:raise ValueError('artifact path')
        expected.add(rel);src=source/rel;no_link(src,source);raw=read_stable(src)
        total+=len(raw)
        if total>256*1024*1024 or len(raw)!=row['bytes'] or hashlib.sha256(raw).hexdigest()!=row['sha256']:raise ValueError('artifact pin/size')
        dst=dest/rel;no_link(dst,dest)
        if dst.exists():
            if read_stable(dst)!=raw:raise ValueError('existing runtime artifact differs')
        else:
            dst.parent.mkdir(parents=True,exist_ok=True)
            with dst.open('xb') as f:f.write(raw)
    found={p.relative_to(dest) for p in dest.rglob('*') if p.is_file()}
    if found!=expected:raise ValueError('runtime has unlisted or missing files')
    return {'files':len(expected),'bytes':total}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--stand',type=Path,required=True);a=p.parse_args()
    local=(ROOT/'local').resolve(strict=True);no_link(a.stand,local);stand=a.stand.resolve(strict=True)
    if not stand.is_relative_to(local/'stands'):raise ValueError('stand outside checkout')
    snap=json.loads(read_stable(stand/'snapshot-receipt.json'));source=Path(snap['source_stand']).resolve(strict=True);source_local=source.parent.parent
    profiles=json.loads(read_stable(stand/'battle-profiles.json'));done={}
    for profile in profiles['profiles']:
        pool=Path(profile['pool']['path']);no_link(pool,stand);data=json.loads(read_stable(pool));worker=data['worker']
        exe=Path(worker['executable']);manifest=Path(worker['artifact_manifest']);no_link(exe,stand);no_link(manifest,stand)
        destination=exe.parent.resolve(strict=True)
        if destination in done:continue
        if destination.is_relative_to(stand/'resources'):origin=source_local/destination.relative_to(stand/'resources')
        elif destination.is_relative_to(stand):origin=source/destination.relative_to(stand)
        else:raise ValueError('worker outside stand')
        no_link(origin,source_local)
        raw=read_stable(manifest)
        if hashlib.sha256(raw).hexdigest()!=worker['artifact_manifest_sha256']:raise ValueError('worker manifest pin')
        manifest_data=json.loads(raw)
        if set(manifest_data)!={'version','files'} or manifest_data['version']!=1:raise ValueError('worker manifest schema')
        done[str(destination)]=stage_runtime(origin,destination,manifest_data['files'])
    write_json(stand/'worker-assets-receipt.json',{'status':'STAGED_NOT_READY','runtimes':done})
    print(json.dumps({'status':'STAGED_NOT_READY','runtime_directories':len(done)}))
if __name__=='__main__':
    try:main()
    except (OSError,ValueError,KeyError,json.JSONDecodeError) as e:
        print('worker binding refused: '+type(e).__name__+': '+str(e),file=sys.stderr);raise SystemExit(1)
