"""Offline locked test-lab gateway release build with immutable input receipt.

Does not launch the gateway. Creates only a fresh directory under local/build.
"""
from pathlib import Path
import argparse,hashlib,json,os,subprocess,sys
from tools.content0_s5a_stand import ROOT,no_link,write_json

def hash_file(path):
    before=path.stat();h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
    after=path.stat()
    if (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):raise ValueError('input changed during hashing')
    return h.hexdigest()

def checkout_fingerprint(root):
    root=Path(root).resolve(strict=True)
    names=subprocess.check_output(['git','-C',str(root),'ls-files','-z','--cached','--others','--exclude-standard']).split(b'\0')
    digest=hashlib.sha256();count=0
    for raw in sorted(set(names)):
        if not raw:continue
        name=os.fsdecode(raw);p=root/name
        if p.is_symlink():raise ValueError('linked checkout input refused')
        digest.update(raw);digest.update(b'\0')
        if p.is_file():digest.update(hash_file(p).encode('ascii'))
        else:digest.update(b'MISSING')
        digest.update(b'\0');count+=1
    commit=subprocess.check_output(['git','-C',str(root),'rev-parse','HEAD'],text=True).strip()
    return {'git_head':commit,'tracked_and_untracked_files':count,'content_sha256':digest.hexdigest()}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',required=True,type=Path);a=p.parse_args()
    local=(ROOT/'local').resolve(strict=True);no_link(a.out,local);out=a.out.resolve()
    if not out.is_relative_to(local/'build') or out.exists():raise ValueError('fresh checkout local/build path required')
    vendor=ROOT/'local/vendor/wg-toolkit-rs';source_before=checkout_fingerprint(ROOT);vendor_before=checkout_fingerprint(vendor)
    tools=Path('D:/WoT_9.1_Server/local/toolchains');rust=tools/'rustup/toolchains/1.90.0-x86_64-pc-windows-gnu';native=rust/'lib/rustlib/x86_64-pc-windows-gnu';linker=native/'bin/self-contained';lib=native/'lib/self-contained';cargo=rust/'bin/cargo.exe'
    env=os.environ.copy();env.update({'CARGO_HOME':str(tools/'cargo'),'RUSTUP_HOME':str(tools/'rustup'),'CARGO_TARGET_DIR':str(out/'target'),
        'CARGO_TARGET_X86_64_PC_WINDOWS_GNU_LINKER':str(linker/'x86_64-w64-mingw32-gcc.exe'),
        'RUSTFLAGS':'-L native='+lib.as_posix()+' -C link-arg=-B'+linker.as_posix()+'/',
        'LIBRARY_PATH':str(lib),'PATH':os.pathsep.join(map(str,[linker,tools/'llvm-mingw-20250910-ucrt-x86_64/bin',rust/'bin',tools/'cargo/bin']))+os.pathsep+env.get('PATH','')})
    command=[str(cargo),'build','--release','--offline','--locked','--manifest-path',str(ROOT/'server/gateway/Cargo.toml'),'--features','test_lab']
    out.mkdir(parents=True)
    with (out/'build.log').open('xb') as log:result=subprocess.run(command,cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT)
    executable=out/'target/release/sr-gateway.exe';source_after=checkout_fingerprint(ROOT);vendor_after=checkout_fingerprint(vendor)
    if result.returncode!=0 or not executable.is_file() or source_before!=source_after or vendor_before!=vendor_after:
        write_json(out/'receipt.json',{'status':'FAIL','exit':result.returncode,'source_before':source_before,'source_after':source_after,'vendor_before':vendor_before,'vendor_after':vendor_after})
        raise ValueError('build failed or inputs changed; inspect local build log')
    receipt={'status':'PASS_BUILD_ONLY','feature':'test_lab','offline_locked':True,'source':source_before,'vendor':vendor_before,
        'command':command,'rustflags':env['RUSTFLAGS'],'cargo_sha256':hash_file(cargo),
        'rustc_sha256':hash_file(rust/'bin/rustc.exe'),'linker_sha256':hash_file(linker/'x86_64-w64-mingw32-gcc.exe'),
        'executable':str(executable),'executable_sha256':hash_file(executable),'native':'NOT_RUN'}
    write_json(out/'receipt.json',receipt);print(json.dumps({'status':receipt['status'],'receipt':str(out/'receipt.json')}))

if __name__=='__main__':
    try:main()
    except (OSError,ValueError,subprocess.SubprocessError) as e:
        print('build refused: '+type(e).__name__+': '+str(e),file=sys.stderr);raise SystemExit(1)
