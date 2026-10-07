"""Own one persistent lab gateway and sequential native-client runs, with rollback."""
import argparse
import hashlib
import json
import subprocess
import shutil
import sys
import time
from pathlib import Path
from cryptography.hazmat.primitives import serialization
from client_audit import ROOT,output_dir,read_limited,save_json,sha256,config
from verify_redirect_capture import login_plaintext,login_fields

CASES=('normal','drop-server-first','drop-client-ack','duplicate-client-first','wrong-password','blackhole','drop-server-sync','duplicate-client-sync')

def run(args):
    source=output_dir(args.source);out=output_dir(args.out)
    if any(out.iterdir()):raise ValueError('suite output must be empty')
    fixture = None
    if args.hangar_stage == 'gui':
        if not args.account_probe or not args.account_bootstrap or not args.hangar_fixture:
            raise ValueError('GUI requires explicit Account bootstrap and own hangar fixture')
        fixture = (ROOT/args.hangar_fixture).resolve(strict=True)
        if not fixture.is_relative_to(config()[1]['local_artifacts_root']):
            raise ValueError('hangar fixture must be under local/')
        snapshot = out/'fixture'
        snapshot.mkdir()
        for name in ('state.bin','shop.bin','dossier.bin','manifest.json'):
            read_limited(fixture/name, 65536)
            shutil.copy2(fixture/name, snapshot/name)
        fixture = snapshot
    cases=args.cases.split(',')
    if not 1<=len(cases)<=16 or any(x not in CASES for x in cases):raise ValueError('invalid bounded case list')
    capture=json.loads(read_limited(source/'capture.json',256*1024))
    row=next(r for r in capture['packets'] if r['direction']=='client_to_server')
    packet=read_limited(source/row['file'],1024)
    if hashlib.sha256(packet).hexdigest()!=row['sha256']:raise ValueError('source packet hash')
    old=serialization.load_pem_private_key(read_limited(source/'test-private.pem',16384),None)
    plain=login_plaintext(packet,old);login_fields(plain);digest=plain[-20:-4]
    if args.digest_mismatch:digest=bytes([digest[0]^128])+digest[1:]
    (out/'client-digest.bin').write_bytes(digest)
    save_json(out/'digest-source.json',{'packet':str(source/row['file']),'sha256':row['sha256'],'digest_sha256':hashlib.sha256(digest).hexdigest(),'intentional_mismatch':args.digest_mismatch})
    private=out/'test-private.pem';openssl=Path('C:/Program Files/Git/usr/bin/openssl.exe')
    subprocess.run([str(openssl),'genpkey','-algorithm','RSA','-pkeyopt','rsa_keygen_bits:1024','-out',str(private)],check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=15)
    backend=(ROOT/'local/vendor/wg-toolkit-rs/target/debug/p01-wg-probe.exe').resolve(strict=True)
    process=None;rows=[];completed=False
    startup=subprocess.STARTUPINFO();startup.dwFlags|=subprocess.STARTF_USESHOWWINDOW;startup.wShowWindow=0
    try:
        with (out/'gateway.stdout.log').open('wb') as stdout,(out/'gateway.stderr.log').open('wb') as stderr:
            profile='legacy091-account' if args.account_probe else 'legacy091-gateway'
            if args.account_probe and args.account_bootstrap:profile='legacy091-account-ready'
            if fixture:profile='legacy091-hangar'
            backend_command=[str(backend),profile,str(private),str(out/'client-digest.bin')]
            if fixture:backend_command.append(str(fixture))
            process=subprocess.Popen(backend_command,cwd=ROOT,stdout=stdout,stderr=stderr,startupinfo=startup,creationflags=subprocess.CREATE_NO_WINDOW)
            save_json(out/'gateway.json',{'pid':process.pid,'profile':profile,'exe':str(backend),'binary_sha256':sha256(backend),'private_key':str(private),'stdout':str(out/'gateway.stdout.log'),'stderr':str(out/'gateway.stderr.log')})
            deadline=time.monotonic()+5
            while 'BOUND ' not in (out/'gateway.stdout.log').read_text():
                if process.poll() is not None or time.monotonic()>deadline:raise RuntimeError('gateway failed to bind')
                time.sleep(0.05)
            for index,case in enumerate(cases,1):
                if process.poll() is not None:raise RuntimeError('persistent gateway exited between clients')
                runout=out/f'{index:02d}-{case}';runout.mkdir()
                seconds=16 if case=='blackhole' else 9 if case=='wrong-password' or args.digest_mismatch else 15
                if args.hangar_stage == 'gui' and case not in ('wrong-password','blackhole') and not args.digest_mismatch:seconds=30
                command=[sys.executable,'-X','utf8','tools/client_probe.py','run','--out',str(runout),'--backend',str(backend),'--backend-profile','legacy091-gateway','--external-backend',str(out/'gateway.json'),'--probe-seconds',str(seconds)]
                if case=='wrong-password':command+=['--bad-password']
                elif case!='normal':command+=['--network-fault',case]
                if args.account_probe or args.observe_account:command+=['--observe-account']
                if args.account_bootstrap:command+=['--account-bootstrap']
                if args.hangar_stage:command+=['--hangar-stage',args.hangar_stage]
                if args.hangar_stage == 'gui':command+=['--timeout','60']
                if args.diagnostic_no_license_dialog:command+=['--diagnostic-no-license-dialog']
                if args.visible_hangar:command+=['--visible-hangar']
                if args.diagnostic_open_profile:command+=['--diagnostic-open-profile']
                with (runout/'runner.log').open('wb') as log:
                    result=subprocess.run(command,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,timeout=65)
                rows.append({'case':case,'run':runout.name,'runner_exit':result.returncode,'gateway_pid':process.pid,'gateway_alive':process.poll() is None})
                print(json.dumps(rows[-1]),flush=True)
                if result.returncode or process.poll() is not None:raise RuntimeError('native runner/gateway failed; inspect retained run')
                time.sleep(0.3)
        completed=True
    finally:
        if process is not None and process.poll() is None:process.terminate();process.wait(timeout=5)
        save_json(out/'suite.json',{'runner_status':'PASS' if completed else 'FAIL','compatibility_status':'NOT_RUN','account_probe':args.account_probe,'account_bootstrap':args.account_bootstrap,'hangar_stage':args.hangar_stage,'diagnostic_open_profile':args.diagnostic_open_profile,'fixture':str(fixture) if fixture else None,'cases':rows,'gateway_stopped':process is None or process.poll() is not None,'scope':'Native compatibility requires an independent capture verifier; process success alone is insufficient'})

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',required=True);parser.add_argument('--out',required=True)
    parser.add_argument('--cases',default='normal');parser.add_argument('--digest-mismatch',action='store_true')
    parser.add_argument('--account-probe',action='store_true',help='opt-in first native Account creation experiment; requires separate evidence verification')
    parser.add_argument('--observe-account',action='store_true',help='passively observe native player also in the no-creation control')
    parser.add_argument('--account-bootstrap',action='store_true',help='initialize original Account dependencies in isolated preferences')
    parser.add_argument('--hangar-stage',choices=('extract','gui'))
    parser.add_argument('--hangar-fixture',help='own bounded fixture under local/')
    parser.add_argument('--diagnostic-no-license-dialog',action='store_true')
    parser.add_argument('--visible-hangar',action='store_true')
    parser.add_argument('--diagnostic-open-profile',action='store_true')
    run(parser.parse_args())
