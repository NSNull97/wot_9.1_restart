"""Update only an inactive isolated stand to the pinned foliage v2 artifact."""
import argparse,hashlib,json,os,sys
from pathlib import Path
from tools.content0_s5a_stand import ROOT,no_link,read_stable,write_json
from tools.content0_s5a_configure import FOLIAGE_SHA

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--stand',type=Path,required=True);a=p.parse_args()
    local=(ROOT/'local').resolve(strict=True);no_link(a.stand,local);stand=a.stand.resolve(strict=True)
    if not stand.is_relative_to(local/'stands'):raise ValueError('stand outside own checkout')
    receipt=json.loads(read_stable(stand/'config-receipt.json'));gateway=json.loads(read_stable(stand/'gateway.json'))
    if receipt['status']!='CONFIGURED_NOT_LAUNCHED' or hashlib.sha256(read_stable(stand/'gateway.json')).hexdigest()!=receipt['config_sha256']['gateway']:
        raise ValueError('gateway configuration changed')
    raw=read_stable(ROOT/'local/evidence/20261114-s5a-bush-volumes-02/volumes.json')
    if hashlib.sha256(raw).hexdigest()!=FOLIAGE_SHA:raise ValueError('foliage v2 pin mismatch')
    doc=json.loads(raw)
    if set(('fire_near_distance_m','fire_near_multiplier'))-doc.keys():raise ValueError('foliage v2 fire calibration missing')
    target=stand/'runtime/foliage-v2.json'
    with target.open('xb') as f:f.write(raw)
    gateway['foliage_v1']={'version':1,'file':str(target),'sha256':FOLIAGE_SHA}
    temp=stand/'gateway.next.json'
    if temp.exists():raise ValueError('pending gateway config')
    write_json(temp,gateway);os.replace(temp,stand/'gateway.json')
    receipt['config_sha256']['gateway']=hashlib.sha256(read_stable(stand/'gateway.json')).hexdigest()
    receipt['foliage_sha256']=FOLIAGE_SHA;write_json(stand/'config-receipt.json',receipt)
    print('foliage v2 pinned; native runtime NOT_RUN')
if __name__=='__main__':
    try:main()
    except (OSError,ValueError,KeyError,json.JSONDecodeError) as e:
        print('foliage update refused: '+type(e).__name__+': '+str(e),file=sys.stderr);raise SystemExit(1)
