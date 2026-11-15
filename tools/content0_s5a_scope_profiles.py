"""Scope a closed 5a stand to pinned qualified scouts and five base profiles."""
import argparse,hashlib,json,os,sys
from pathlib import Path
from tools.content0_s5a_stand import ROOT,no_link,read_stable,write_json
KINDS=('china-Ch17_WZ131_1_WZ132','france-AMX_13_75','usa-T71')
BASE=('ms1','is7','t26','t34','t3485')
FIELDS=('body_half_extents','body_center_offset','wheel_points','mass_kg','max_forward_mps','max_reverse_mps','engine_max_torque_nm','wheel_radius','suspension_min','suspension_max','track_max_brake_torque','longitudinal_friction','lateral_friction','stationary_steering_ratio')
def check_projection(qualified,configs):
    physics=qualified['definition']['physics'];handling=qualified['definition']['handling']
    for c in configs:
        if any(c[k]!=physics[k] for k in FIELDS) or c['handling']!=handling:raise ValueError('qualified physics differs from pool configuration')

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--stand',type=Path,required=True);p.add_argument('--qualification-dir',type=Path,required=True);a=p.parse_args()
    local=(ROOT/'local').resolve(strict=True);no_link(a.stand,local);stand=a.stand.resolve(strict=True)
    if not stand.is_relative_to(local/'stands'):raise ValueError('stand outside checkout')
    receipt=json.loads(read_stable(stand/'config-receipt.json'));snapshot=json.loads(read_stable(stand/'snapshot-receipt.json'))
    if receipt['status']!='CONFIGURED_NOT_LAUNCHED' or snapshot['status']!='STAGED_NOT_READY':raise ValueError('stand not inactive and configured')
    manifest=json.loads(read_stable(stand/'battle-profiles.json'));registry=json.loads(read_stable(ROOT/'config/test_lab/battle_qualification.v1.json'))
    qual={row['kind']:row for row in registry['profiles']};by_kind={row['kind']:row for row in manifest['profiles']}
    if len(by_kind)!=len(manifest['profiles']) or any(k not in by_kind for k in BASE+KINDS):raise ValueError('missing or duplicate roster profile')
    source=a.qualification_dir.resolve(strict=True);out=stand/'qualified-scouts-v1';out.mkdir()
    scoped=[by_kind[k] for k in BASE]
    for kind in KINDS:
        record=qual[kind];path=source/record['file'];no_link(path,source);raw=read_stable(path)
        if len(raw)!=record['bytes'] or hashlib.sha256(raw).hexdigest()!=record['sha256']:raise ValueError('qualification pin mismatch')
        qualified=json.loads(raw);profile=by_kind[kind];pool_path=Path(profile['pool']['path']);no_link(pool_path,stand)
        pool=json.loads(read_stable(pool_path));configs=[]
        for row in pool['maps']:
            path=Path(row['config']);no_link(path,stand);config_raw=read_stable(path)
            if hashlib.sha256(config_raw).hexdigest()!=row['config_sha256']:raise ValueError('map config pin mismatch')
            configs.append(json.loads(config_raw))
        check_projection(qualified,configs)
        destination=out/record['file']
        with destination.open('xb') as f:f.write(raw)
        pool['vehicle_profile']={'path':str(destination),'sha256':record['sha256']}
        new_pool=out/(kind+'-pool.json');write_json(new_pool,pool)
        profile['pool']={'path':str(new_pool),'sha256':hashlib.sha256(read_stable(new_pool)).hexdigest()};scoped.append(profile)
    manifest['profiles']=scoped;temporary=stand/'battle-profiles.scoped.json'
    if temporary.exists():raise ValueError('pending profile manifest')
    write_json(temporary,manifest);os.replace(temporary,stand/'battle-profiles.json')
    receipt['battle_profiles_sha256']=hashlib.sha256(read_stable(stand/'battle-profiles.json')).hexdigest();receipt['profile_roster']=list(BASE+KINDS)
    write_json(stand/'config-receipt.json',receipt)
    write_json(stand/'scoped-profiles-receipt.json',{'status':'STAGED_NOT_READY','roster':list(BASE+KINDS),'manifest_sha256':receipt['battle_profiles_sha256'],'qualification_sha256':hashlib.sha256(read_stable(ROOT/'config/test_lab/battle_qualification.v1.json')).hexdigest()})
    print(json.dumps({'status':'STAGED_NOT_READY','profiles':len(scoped)}))
if __name__=='__main__':
    try:main()
    except (OSError,ValueError,KeyError,json.JSONDecodeError) as e:
        print('profile scoping refused: '+type(e).__name__+': '+str(e),file=sys.stderr);raise SystemExit(1)
