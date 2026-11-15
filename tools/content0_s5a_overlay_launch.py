"""Launch one checked thin overlay only under the audited Windows low token.

The same restricted token performs a fresh read-only source audit and starts
the suspended EXE. The child token is checked before its first instruction.
No existing client is touched or terminated. Native compatibility is NOT_RUN.
"""
import argparse
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from client_audit import ROOT, config, save_json, sha256
from content0_s5a_overlay import checked_overlay, verify_source
from destructible_catalog import no_links
from instance_mutex import observe
import interactive_client
from tools.content0_s5a_configure import restrict_directory
from tools import content0_s5a_integrity_probe as probe

LOW_RID = 4096


def environment(overlay, base):
    root = Path(overlay)
    folders = {name: root / 'runtime' / name.lower() for name in
               ('APPDATA', 'LOCALAPPDATA', 'USERPROFILE', 'TEMP', 'TMP', 'PROGRAMDATA', 'PUBLIC')}
    for directory in folders.values():
        no_links(directory)
        directory.mkdir(parents=True, exist_ok=True)
    # A low token is not a read sandbox. Do not pass host secrets, proxy
    # settings or arbitrary process configuration to the native client.
    upper={key.upper():value for key,value in base.items()}
    systemroot=upper.get('SYSTEMROOT')
    if not systemroot or '\0' in systemroot:raise ValueError('Windows SYSTEMROOT required')
    allowed=('SYSTEMROOT','WINDIR','SYSTEMDRIVE','COMSPEC','OS','PROCESSOR_ARCHITECTURE',
             'PROCESSOR_IDENTIFIER','NUMBER_OF_PROCESSORS','PATHEXT')
    env={key:upper[key] for key in allowed if key in upper and isinstance(upper[key],str) and '\0' not in upper[key]}
    env['PATH']=str(Path(systemroot)/'System32')+os.pathsep+systemroot
    env.update({name: str(value) for name, value in folders.items()})
    # Avoid legacy consumers following the real home directory.
    drive, tail = os.path.splitdrive(str(folders['USERPROFILE']))
    env['HOMEDRIVE'], env['HOMEPATH'] = drive, tail
    return env


def inspect_installed(out, root, plan):
    if plan.get('thin_overlay') is not True or Path(plan['research_root']) != root:
        raise ValueError('explicit thin-overlay plan required')
    ledger_path = no_links(out/'patch-ledger.json').resolve(strict=True)
    ledger = json.loads(ledger_path.read_text(encoding='utf-8-sig'))
    if ledger.get('plan_sha256') != sha256(out/'install-plan.json'):
        raise ValueError('overlay ledger differs from plan')
    if not (out/'install.json').is_file() or (out/'restore.json').exists():
        raise ValueError('active installed ledger required')
    for entry in plan['files']:
        if not entry['runtime_mutable']:
            file = interactive_client.target(root, entry['path'])
            if interactive_client.file_hash(file) != entry['installed_sha256']:
                raise ValueError('installed overlay payload differs: ' + entry['path'])
    return sha256(ledger_path)


def verify_before_resume(backend, process):
    """On failure terminate only our never-resumed suspended child."""
    try:
        if backend.process_rid(process) != LOW_RID:
            raise ValueError('new process token is not low integrity')
        backend.resume(process)
    except Exception:
        backend.terminate_suspended(process)
        raise


class WindowsLowToken:
    def __init__(self):
        self.token = probe.HANDLE(); self.restricted = probe.HANDLE(); self.sid = probe.LPVOID()
        probe.win(probe.a.OpenProcessToken(probe.k.GetCurrentProcess(),0x0001|0x0002|0x0008|0x0080,ctypes.byref(self.token)))
        try:
            probe.win(probe.a.CreateRestrictedToken(self.token,1,0,None,0,None,0,None,ctypes.byref(self.restricted)))
            probe.win(probe.a.ConvertStringSidToSidW('S-1-16-4096',ctypes.byref(self.sid)))
            label=probe.TOKEN_MANDATORY_LABEL(probe.SID_AND_ATTRIBUTES(self.sid,0x20))
            probe.win(probe.a.SetTokenInformation(self.restricted,25,ctypes.byref(label),ctypes.sizeof(label)+probe.a.GetLengthSid(self.sid)))
        except Exception:
            self.close(); raise

    def create_suspended(self, executable, args, cwd, env):
        pi=probe.PROCESS_INFORMATION();start=probe.STARTUPINFO();start.cb=ctypes.sizeof(start)
        command=ctypes.create_unicode_buffer(subprocess.list2cmdline([str(executable),*map(str,args)]))
        # Sorted UTF-16 Windows environment block; no handles are inherited.
        block=ctypes.create_unicode_buffer('\0'.join(k+'='+v for k,v in sorted(env.items(),key=lambda item:item[0].upper()))+'\0\0')
        flags=0x00000004|0x00000400  # CREATE_SUSPENDED | CREATE_UNICODE_ENVIRONMENT
        probe.win(probe.a.CreateProcessAsUserW(self.restricted,str(executable),command,None,None,False,flags,
            ctypes.cast(block,probe.LPVOID),str(cwd),ctypes.byref(start),ctypes.byref(pi)))
        return pi

    def process_rid(self, process):
        token=probe.HANDLE();probe.win(probe.a.OpenProcessToken(process.hProcess,8,ctypes.byref(token)))
        try:
            need=probe.DWORD();probe.a.GetTokenInformation(token,25,None,0,ctypes.byref(need))
            buf=ctypes.create_string_buffer(need.value)
            probe.win(probe.a.GetTokenInformation(token,25,buf,need,ctypes.byref(need)))
            sid=ctypes.cast(buf,ctypes.POINTER(probe.TOKEN_MANDATORY_LABEL)).contents.Label.Sid
            n=probe.a.GetSidSubAuthorityCount(sid).contents.value
            return probe.a.GetSidSubAuthority(sid,n-1).contents.value
        finally:probe.k.CloseHandle(token)

    def resume(self, process):
        probe.k.ResumeThread.argtypes=[probe.HANDLE];probe.k.ResumeThread.restype=probe.DWORD
        if probe.k.ResumeThread(process.hThread)==0xffffffff:raise ctypes.WinError(ctypes.get_last_error())

    def terminate_suspended(self, process):
        probe.k.TerminateProcess.argtypes=[probe.HANDLE,probe.DWORD];probe.k.TerminateProcess.restype=probe.BOOL
        probe.win(probe.k.TerminateProcess(process.hProcess,1))

    def close_process(self, process):
        if process.hThread:probe.k.CloseHandle(process.hThread)
        if process.hProcess:probe.k.CloseHandle(process.hProcess)

    def close(self):
        if self.sid:probe.k.LocalFree(self.sid);self.sid=probe.LPVOID()
        if self.restricted:probe.k.CloseHandle(self.restricted);self.restricted=probe.HANDLE()
        if self.token:probe.k.CloseHandle(self.token);self.token=probe.HANDLE()


def launch(install_dir, evidence_dir):
    _,paths=config()
    args=argparse.Namespace(out=install_dir)
    out, root, plan=interactive_client.load_plan(args)
    root, marker=checked_overlay(root,paths)
    if out == root or out.is_relative_to(root):
        raise ValueError('installer plan and ledger must remain outside the low overlay')
    ledger_sha=inspect_installed(out,root,plan)
    verify_source(marker)
    local=paths['local_artifacts_root'].resolve(strict=True)
    if plan['settings'].get('enable_profile13_fight_test') is True:
        from profile13_fight_binding import from_receipt
        binding=from_receipt(plan.get('profile13_fight_stand_receipt'),local,plan['settings']['visibility_debug'],plan['settings']['endpoint'])
        if binding!=plan['settings'].get('profile13_fight_binding'):
            raise ValueError('live operator UUID/native ID binding changed since prepare')
    evidence=no_links(evidence_dir).resolve()
    if not evidence.is_relative_to(local/'evidence') or evidence.exists():
        raise ValueError('fresh medium evidence directory required')
    evidence.mkdir(parents=True);restrict_directory(evidence)
    control=evidence/'medium-control.txt';control.write_text('owned control',encoding='ascii')
    env=environment(root,os.environ)
    probe_dir=root/'runtime'/'low-probes'/uuid.uuid4().hex
    no_links(probe_dir);probe_dir.mkdir(parents=True)
    result_path=probe_dir/'result.json'
    source_inventory=probe.snapshot_inventory(Path(marker['source']))
    protected_inventory=probe.snapshot_inventory(out)
    backend=WindowsLowToken()
    try:
        # EXACT same restricted token is retained for both processes.
        child=backend.create_suspended(sys.executable,['-B','-m','tools.content0_s5a_integrity_probe',
            '--child','--source',str(marker['source']),'--out',str(result_path),'--control',str(control),
            '--protect',str(out),'--expected-source',source_inventory,'--expected-protected',protected_inventory],ROOT,env)
        try:
            verify_before_resume(backend,child)
            if probe.k.WaitForSingleObject(child.hProcess,180000)!=0:raise TimeoutError('source audit timed out')
            code=probe.DWORD();probe.win(probe.k.GetExitCodeProcess(child.hProcess,ctypes.byref(code)))
            if code.value!=0:raise ValueError('low-token source audit failed')
        finally:backend.close_process(child)
        raw=result_path.read_bytes()
        if len(raw)>65536:raise ValueError('audit result size')
        result=json.loads(raw)
        if (result.get('token_integrity_rid')!=LOW_RID or result.get('unexpected_count')!=0
                or result.get('packages_read_opened')!=63 or result.get('package_read_failures')!=0
                or result.get('protected_count',0)<1 or result.get('protected_unexpected_count')!=0
                or result.get('ancestor_unexpected_count')!=0
                or result.get('source_inventory_sha256')!=source_inventory
                or result.get('protected_inventory_sha256')!=protected_inventory
                or not result.get('medium_control_write_denied')):
            raise ValueError('source audit did not establish no-write-up')
        if observe(marker['instance_mutex'])['exists']:raise ValueError('overlay instance already running')
        # Lock the evidence before the client gets to write its own overlay.
        save_json(evidence/'prelaunch.json',{'schema':'content0-s5a-overlay-launch.v1',
            'overlay':str(root),'marker_sha256':sha256(root/'content0_s5a_overlay.json'),
            'ledger_sha256':ledger_sha,'source_audit':result,'native':'NOT_RUN'})
        game=backend.create_suspended(root/'WorldOfTanks.exe',[],root,env)
        try:
            verify_before_resume(backend,game)
            save_json(evidence/'started.json',{'pid':game.dwProcessId,'integrity_rid':LOW_RID,
                      'scope':'owned thin overlay','native_compatibility':'NOT_RUN'})
            return game.dwProcessId
        finally:backend.close_process(game)
    finally:backend.close()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--install-dir',required=True);parser.add_argument('--evidence-dir',required=True)
    args=parser.parse_args(); print('started PID',launch(args.install_dir,args.evidence_dir))


if __name__=='__main__':main()
