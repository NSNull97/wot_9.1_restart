"""Produce immutable on/off bot-net configurations, never restart a battle."""
import argparse,copy,hashlib,json,sys
from pathlib import Path
from tools.content0_s5a_stand import ROOT,no_link,read_stable,write_json

def variants(config):
    scenario=config['fixed_scout_v1'];seats=scenario['seats']
    if scenario['version']!=1 or len(seats)!=4 or seats[0]['kind']!='human' or seats[0]['net'] is not False or scenario['events']!=[]:raise ValueError('unexpected fixed scout baseline')
    kinds=('china-Ch17_WZ131_1_WZ132','france-AMX_13_75','usa-T71')
    if tuple(row['kind'] for row in seats[1:])!=kinds or any(type(row['net']) is not bool for row in seats[1:]):raise ValueError('unexpected scout roster')
    result={}
    for enabled in (False,True):
        variant=copy.deepcopy(config)
        for seat in variant['fixed_scout_v1']['seats'][1:]:seat['net']=enabled
        result['net-on' if enabled else 'net-off']=variant
    return result

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--stand',required=True,type=Path);a=p.parse_args()
    local=(ROOT/'local').resolve(strict=True);no_link(a.stand,local);stand=a.stand.resolve(strict=True)
    if not stand.is_relative_to(local/'stands'):raise ValueError('stand outside checkout')
    receipt=json.loads(read_stable(stand/'config-receipt.json'));raw=read_stable(stand/'gateway.json')
    if hashlib.sha256(raw).hexdigest()!=receipt['config_sha256']['gateway']:raise ValueError('baseline config differs from receipt')
    rows=variants(json.loads(raw));out=stand/'variants-v1';out.mkdir()
    result={}
    for name,value in rows.items():
        path=out/(name+'.gateway.json');write_json(path,value);result[name]={'path':str(path),'sha256':hashlib.sha256(read_stable(path)).hexdigest()}
    write_json(out/'receipt.json',{'schema':'content0-s5a-scout-net-variants.v1','status':'PREPARED_NOT_RUN','base_gateway_sha256':receipt['config_sha256']['gateway'],'variants':result,'run_binding':'new gateway run and new client grant binding required'})
    print(json.dumps({'status':'PREPARED_NOT_RUN','receipt':str(out/'receipt.json')}))
if __name__=='__main__':
    try:main()
    except (OSError,ValueError,KeyError,json.JSONDecodeError) as e:print('variant preparation refused: '+type(e).__name__+': '+str(e),file=sys.stderr);raise SystemExit(1)
