"""Probe Windows low-integrity access without launching or modifying the client.

The source tree is only enumerated/opened with OPEN_EXISTING. No bytes or ACLs
there are changed. The only writes are inside a fresh owned evidence directory.
"""
import argparse,ctypes,hashlib,json,os,subprocess,sys,time
from ctypes import wintypes
from pathlib import Path
from tools.content0_s5a_stand import ROOT,no_link,write_json
from tools.content0_s5a_configure import restrict_directory

if os.name!='nt':raise SystemExit('Windows required')
k=ctypes.WinDLL('kernel32',use_last_error=True);a=ctypes.WinDLL('advapi32',use_last_error=True)
HANDLE=wintypes.HANDLE;DWORD=wintypes.DWORD;BOOL=wintypes.BOOL;LPVOID=ctypes.c_void_p
k.GetCurrentProcess.restype=HANDLE
k.CreateFileW.argtypes=[wintypes.LPCWSTR,DWORD,DWORD,LPVOID,DWORD,DWORD,HANDLE];k.CreateFileW.restype=HANDLE
k.CloseHandle.argtypes=[HANDLE];k.CloseHandle.restype=BOOL
k.GetLastError.restype=DWORD
k.WaitForSingleObject.argtypes=[HANDLE,DWORD];k.WaitForSingleObject.restype=DWORD
k.GetExitCodeProcess.argtypes=[HANDLE,ctypes.POINTER(DWORD)];k.GetExitCodeProcess.restype=BOOL
k.LocalFree.argtypes=[HANDLE];k.LocalFree.restype=HANDLE
a.OpenProcessToken.argtypes=[HANDLE,DWORD,ctypes.POINTER(HANDLE)];a.OpenProcessToken.restype=BOOL
a.CreateRestrictedToken.argtypes=[HANDLE,DWORD,DWORD,LPVOID,DWORD,LPVOID,DWORD,LPVOID,ctypes.POINTER(HANDLE)];a.CreateRestrictedToken.restype=BOOL
a.ConvertStringSidToSidW.argtypes=[wintypes.LPCWSTR,ctypes.POINTER(LPVOID)];a.ConvertStringSidToSidW.restype=BOOL
a.GetLengthSid.argtypes=[LPVOID];a.GetLengthSid.restype=DWORD
a.SetTokenInformation.argtypes=[HANDLE,DWORD,LPVOID,DWORD];a.SetTokenInformation.restype=BOOL
a.GetTokenInformation.argtypes=[HANDLE,DWORD,LPVOID,DWORD,ctypes.POINTER(DWORD)];a.GetTokenInformation.restype=BOOL
a.GetSidSubAuthorityCount.argtypes=[LPVOID];a.GetSidSubAuthorityCount.restype=ctypes.POINTER(ctypes.c_ubyte)
a.GetSidSubAuthority.argtypes=[LPVOID,DWORD];a.GetSidSubAuthority.restype=ctypes.POINTER(DWORD)
class SID_AND_ATTRIBUTES(ctypes.Structure):_fields_=[('Sid',LPVOID),('Attributes',DWORD)]
class TOKEN_MANDATORY_LABEL(ctypes.Structure):_fields_=[('Label',SID_AND_ATTRIBUTES)]
class STARTUPINFO(ctypes.Structure):
    _fields_=[('cb',DWORD),('lpReserved',wintypes.LPWSTR),('lpDesktop',wintypes.LPWSTR),('lpTitle',wintypes.LPWSTR),('dwX',DWORD),('dwY',DWORD),('dwXSize',DWORD),('dwYSize',DWORD),('dwXCountChars',DWORD),('dwYCountChars',DWORD),('dwFillAttribute',DWORD),('dwFlags',DWORD),('wShowWindow',wintypes.WORD),('cbReserved2',wintypes.WORD),('lpReserved2',ctypes.POINTER(ctypes.c_ubyte)),('hStdInput',HANDLE),('hStdOutput',HANDLE),('hStdError',HANDLE)]
class PROCESS_INFORMATION(ctypes.Structure):_fields_=[('hProcess',HANDLE),('hThread',HANDLE),('dwProcessId',DWORD),('dwThreadId',DWORD)]
a.CreateProcessAsUserW.argtypes=[HANDLE,wintypes.LPCWSTR,wintypes.LPWSTR,LPVOID,LPVOID,BOOL,DWORD,LPVOID,wintypes.LPCWSTR,ctypes.POINTER(STARTUPINFO),ctypes.POINTER(PROCESS_INFORMATION)];a.CreateProcessAsUserW.restype=BOOL
INVALID=ctypes.c_void_p(-1).value

def win(ok):
    if not ok:raise ctypes.WinError(ctypes.get_last_error())

def integrity_rid():
    token=HANDLE();win(a.OpenProcessToken(k.GetCurrentProcess(),8,ctypes.byref(token)))
    try:
        needed=DWORD();a.GetTokenInformation(token,25,None,0,ctypes.byref(needed));buf=ctypes.create_string_buffer(needed.value)
        win(a.GetTokenInformation(token,25,buf,needed,ctypes.byref(needed)))
        sid=ctypes.cast(buf,ctypes.POINTER(TOKEN_MANDATORY_LABEL)).contents.Label.Sid
        n=a.GetSidSubAuthorityCount(sid).contents.value;return a.GetSidSubAuthority(sid,n-1).contents.value
    finally:k.CloseHandle(token)

def can_open(path,access,directory=False):
    flags=0x02000000 if directory else 0x80
    h=k.CreateFileW(str(path),access,7,None,3,flags,None)
    if h==INVALID:return False,ctypes.get_last_error()
    k.CloseHandle(h);return True,0

def walk_entries(root):
    root=Path(root)
    if not root.is_dir():raise ValueError('audited directory required')
    def fail(error):raise error
    count=0
    for current,dirs,files in os.walk(root,followlinks=False,onerror=fail):
        for name in dirs+files:
            item=Path(current)/name
            if item.is_symlink() or (hasattr(item,'is_junction') and item.is_junction()):raise ValueError('linked audited entry refused')
        yield Path(current),True
        for name in files:yield Path(current)/name,False
        count+=1+len(files)
        if count>10000:raise ValueError('audited entry bound')

def inventory(rows,root):
    values=sorted(('d:' if directory else 'f:')+item.relative_to(root).as_posix() for item,directory in rows)
    return hashlib.sha256(json.dumps(values,ensure_ascii=True,separators=(',',':')).encode('ascii')).hexdigest()

def snapshot_inventory(root):
    root=Path(root)
    return inventory(list(walk_entries(root)),root)

def child(source,out,control,protect=None,expected_source=None,expected_protected=None):
    if integrity_rid()!=4096:raise ValueError('child token is not low integrity')
    read_ok,read_err=can_open(control,0x80000000);write_ok,write_err=can_open(control,2)
    if not read_ok or write_ok or write_err!=5:raise ValueError('medium control did not enforce no-write-up')
    source=Path(source);rows=list(walk_entries(source));source_digest=inventory(rows,source)
    if expected_source is not None and source_digest!=expected_source:raise ValueError('source inventory changed or unreadable')
    count=0;packages=0;denied=0;unexpected=[];read_fail=0
    for item,directory in rows:
        for access in (2,4,0x10,0x100,0x10000,0x40000,0x80000)+((0x40,) if directory else ()):
            ok,err=can_open(item,access,directory)
            if ok or err!=5:unexpected.append({'kind':'directory' if directory else 'file','access':access,'opened':ok,'error':err})
            else:denied+=1
        count+=1
        if not directory and item.parent.name.lower()=='packages':
            packages+=1;ok,err=can_open(item,0x80000000)
            if not ok:read_fail+=1
    protected_count=0;protected_unexpected=0
    protected_digest=None
    if protect is not None:
        protect=Path(protect);protected_rows=list(walk_entries(protect));protected_digest=inventory(protected_rows,protect)
        if expected_protected is not None and protected_digest!=expected_protected:raise ValueError('protected inventory changed or unreadable')
        for item,directory in protected_rows:
            protected_count+=1
            for access in (2,4,0x10,0x100,0x10000,0x40000,0x80000)+((0x40,) if directory else ()):
                ok,err=can_open(item,access,directory)
                if ok or err!=5:protected_unexpected+=1
    # DELETE on the child is not enough: DELETE_CHILD on any ancestor can
    # remove/rename that child. Check the complete chain to the volume root.
    ancestor_unexpected=0;ancestors=set(source.parents)
    if protect is not None:ancestors.update(protect.parents)
    for parent in ancestors:
        no_link(parent,parent)
        ok,err=can_open(parent,0x40,True)
        if ok or err!=5:ancestor_unexpected+=1
    result={'token_integrity_rid':integrity_rid(),'medium_control_read':read_ok,'medium_control_write_denied':not write_ok and write_err==5,
            'objects_checked':count,'write_delete_acl_attempts_denied':denied,'unexpected':unexpected[:20],
            'unexpected_count':len(unexpected),'packages_read_opened':packages,'package_read_failures':read_fail,
            'protected_count':protected_count,'protected_unexpected_count':protected_unexpected,
            'ancestor_count':len(ancestors),'ancestor_unexpected_count':ancestor_unexpected,
            'source_inventory_sha256':source_digest,'protected_inventory_sha256':protected_digest}
    write_json(out,result)
    if packages!=63 or read_fail or unexpected or protected_unexpected or ancestor_unexpected:raise ValueError('source access safety not established')

def launch_low(script,args,cwd):
    token=HANDLE();restricted=HANDLE();sid=LPVOID();pi=PROCESS_INFORMATION()
    win(a.OpenProcessToken(k.GetCurrentProcess(),0x0001|0x0002|0x0008|0x0080,ctypes.byref(token)))
    try:
        win(a.CreateRestrictedToken(token,1,0,None,0,None,0,None,ctypes.byref(restricted)))
        win(a.ConvertStringSidToSidW('S-1-16-4096',ctypes.byref(sid)))
        label=TOKEN_MANDATORY_LABEL(SID_AND_ATTRIBUTES(sid,0x20))
        win(a.SetTokenInformation(restricted,25,ctypes.byref(label),ctypes.sizeof(label)+a.GetLengthSid(sid)))
        command=ctypes.create_unicode_buffer(subprocess.list2cmdline([sys.executable,'-B','-m','tools.content0_s5a_integrity_probe','--child',*map(str,args)]))
        start=STARTUPINFO();start.cb=ctypes.sizeof(start)
        win(a.CreateProcessAsUserW(restricted,sys.executable,command,None,None,False,0x08000000,None,str(cwd),ctypes.byref(start),ctypes.byref(pi)))
        if k.WaitForSingleObject(pi.hProcess,180000)!=0:raise TimeoutError('low integrity probe timed out')
        code=DWORD();win(k.GetExitCodeProcess(pi.hProcess,ctypes.byref(code)))
        if code.value!=0:raise ValueError('low integrity child failed; inspect own result')
    finally:
        if pi.hThread:k.CloseHandle(pi.hThread)
        if pi.hProcess:k.CloseHandle(pi.hProcess)
        if sid:k.LocalFree(sid)
        if restricted:k.CloseHandle(restricted)
        k.CloseHandle(token)

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--child',action='store_true');p.add_argument('--source',required=True,type=Path);p.add_argument('--out',required=True,type=Path);p.add_argument('--control',type=Path);p.add_argument('--protect',type=Path);p.add_argument('--expected-source');p.add_argument('--expected-protected');args=p.parse_args()
    if args.child:
        if args.control is None:raise ValueError('control required')
        return child(args.source,args.out,args.control,args.protect,args.expected_source,args.expected_protected)
    expected=Path('E:/WoT091_Content0_S5Crew_Client/local/clients/content0-step5-equipment-b').resolve(strict=True)
    if args.source.resolve(strict=True)!=expected:raise ValueError('only the investigated client source')
    local=(ROOT/'local').resolve(strict=True);no_link(args.out,local);out=args.out.resolve()
    if not out.is_relative_to(local/'evidence') or out.exists():raise ValueError('fresh owned evidence directory required')
    out.mkdir(parents=True);control=out/'medium-control.txt';control.write_text('owned control',encoding='ascii');low=out/'low';low.mkdir()
    restrict_directory(low)
    subprocess.run(['icacls',str(low),'/setintegritylevel','(OI)(CI)L'],check=True,capture_output=True)
    source_inventory=snapshot_inventory(expected)
    result=low/'result.json';launch_low(Path(__file__).resolve(),['--source',str(expected),'--out',str(result),'--control',str(control),'--expected-source',source_inventory],ROOT)
    print(json.dumps({'status':'LOW_INTEGRITY_ACCESS_PROBE_PASS','result':str(result),'native':'NOT_RUN'}))
if __name__=='__main__':
    try:main()
    except (OSError,ValueError,TimeoutError,subprocess.SubprocessError) as e:
        print('low integrity probe refused: '+type(e).__name__+': '+str(e),file=sys.stderr);raise SystemExit(1)
