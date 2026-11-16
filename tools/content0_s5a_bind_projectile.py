"""Bind hard-pinned projectile files to an inactive isolated stand's local root."""
import argparse,hashlib,json,os,sys
from pathlib import Path
from tools.content0_s5a_stand import ROOT,no_link,read_stable,write_json

def projectile_files(registry,source_local,asset='02_malinovka'):
    rows=[row for row in registry['maps'] if row.get('asset')==asset]
    if len(rows)!=1:raise ValueError('map registry selection')
    meta=rows[0]['projectile'];rel=Path(meta['manifest_relative'])
    if rel.is_absolute() or '..' in rel.parts:raise ValueError('projectile registry path')
    folder=source_local/rel.parent
    expected={'manifest.json':(meta['manifest_sha256'],meta['manifest_bytes']),
       'obstacles.vertices.f32':(meta['vertices_sha256'],meta['vertex_count']*12),
       'obstacles.triangles.u32':(meta['triangles_sha256'],meta['triangle_count']*12),
       'obstacles.flags.u16':(meta['flags_sha256'],meta['triangle_count']*2)}
    result={}
    for name,(pin,size) in expected.items():
        source=folder/name;no_link(source,source_local);raw=read_stable(source)
        if len(raw)!=size or hashlib.sha256(raw).hexdigest()!=pin:raise ValueError('projectile bytes/pin mismatch')
        result[name]=raw
    return rel.parent,result

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--stand',type=Path,required=True);a=p.parse_args()
    local=(ROOT/'local').resolve(strict=True);no_link(a.stand,local);stand=a.stand.resolve(strict=True)
    if not stand.is_relative_to(local/'stands'):raise ValueError('stand outside own checkout')
    receipt=json.loads(read_stable(stand/'config-receipt.json'));snapshot=json.loads(read_stable(stand/'snapshot-receipt.json'))
    if receipt['status']!='CONFIGURED_NOT_LAUNCHED' or hashlib.sha256(read_stable(stand/'gateway.json')).hexdigest()!=receipt['config_sha256']['gateway']:raise ValueError('gateway config mismatch')
    source_local=Path(snapshot['source_stand']).resolve(strict=True).parent.parent
    registry=json.loads(read_stable(ROOT/'server/contracts/map_registry.json'))
    profiles=json.loads(read_stable(stand/'battle-profiles.json'))
    rel,files=projectile_files(registry,source_local,profiles['map'])
    dest=stand/rel
    if dest.exists():raise ValueError('projectile output exists')
    dest.mkdir(parents=True)
    for name,raw in files.items():
        with (dest/name).open('xb') as f:f.write(raw)
    gateway=json.loads(read_stable(stand/'gateway.json'));gateway['local_root']=str(stand)
    temp=stand/'gateway.next.json'
    if temp.exists():raise ValueError('pending gateway config')
    write_json(temp,gateway);os.replace(temp,stand/'gateway.json')
    receipt['config_sha256']['gateway']=hashlib.sha256(read_stable(stand/'gateway.json')).hexdigest()
    receipt['projectile_manifest_sha256']=hashlib.sha256(files['manifest.json']).hexdigest();write_json(stand/'config-receipt.json',receipt)
    print('pinned projectile files staged; native runtime NOT_RUN')
if __name__=='__main__':
    try:main()
    except (OSError,ValueError,KeyError,json.JSONDecodeError) as e:
        print('projectile binding refused: '+type(e).__name__+': '+str(e),file=sys.stderr);raise SystemExit(1)
