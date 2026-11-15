"""Refresh only the copied resource graph of an inactive isolated snapshot.
Does not access its databases, secrets, client, or any process.
"""
import argparse,hashlib,json,os,sys
from pathlib import Path
from tools.content0_s5a_stand import ROOT,Materializer,no_link,read_stable,json_unique,write_json

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--stand',type=Path,required=True);a=p.parse_args()
    local=(ROOT/'local').resolve(strict=True);no_link(a.stand,local);stand=a.stand.resolve(strict=True)
    if not stand.is_relative_to(local/'stands'):raise ValueError('stand outside checkout')
    receipt=json_unique(read_stable(stand/'snapshot-receipt.json'))
    if receipt.get('status')!='STAGED_NOT_READY' or Path(receipt['output']).resolve()!=stand:raise ValueError('snapshot receipt mismatch')
    source=Path(receipt['source_stand']).resolve(strict=True);source_local=source.parent.parent
    raw=read_stable(source/'battle-profiles.json')
    if hashlib.sha256(raw).hexdigest()!=receipt['source_config_sha256']['battle-profiles.json']:raise ValueError('source profiles changed')
    marker=stand/'resource-refresh-in-progress.json'
    with marker.open('x',encoding='utf8') as f:json.dump({'status':'NOT_READY'},f)
    mat=Materializer(source_local,source,stand,ROOT);profiles=mat.value(json_unique(raw),source)
    temporary=stand/'battle-profiles.refreshed.json'
    if temporary.exists():raise ValueError('refresh output exists')
    write_json(temporary,profiles);os.replace(temporary,stand/'battle-profiles.json')
    receipt['resource_files']=len(mat.done);receipt['unfollowed_terrain_provenance']=mat.terrain_provenance
    receipt['resource_refresh']='PASS_NOT_NATIVE';write_json(stand/'snapshot-receipt.json',receipt)
    marker.unlink();print(json.dumps({'status':'STAGED_NOT_READY','resource_files':len(mat.done)}))
if __name__=='__main__':
    try:main()
    except (OSError,ValueError,KeyError,json.JSONDecodeError) as e:
        print('resource refresh refused: '+type(e).__name__+': '+str(e),file=sys.stderr);raise SystemExit(1)
