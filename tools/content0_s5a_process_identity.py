"""Read immutable Windows process creation identity; no process control."""
import ctypes,os,subprocess
from ctypes import wintypes
from pathlib import Path
if os.name!='nt':raise OSError('Windows required')
k=ctypes.WinDLL('kernel32',use_last_error=True)
k.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD];k.OpenProcess.restype=wintypes.HANDLE
k.GetProcessTimes.argtypes=[wintypes.HANDLE,*([ctypes.POINTER(wintypes.FILETIME)]*4)];k.GetProcessTimes.restype=wintypes.BOOL
k.QueryFullProcessImageNameW.argtypes=[wintypes.HANDLE,wintypes.DWORD,wintypes.LPWSTR,ctypes.POINTER(wintypes.DWORD)];k.QueryFullProcessImageNameW.restype=wintypes.BOOL
k.CloseHandle.argtypes=[wintypes.HANDLE];k.CloseHandle.restype=wintypes.BOOL
k.GetSystemTimeAsFileTime.argtypes=[ctypes.POINTER(wintypes.FILETIME)];k.GetSystemTimeAsFileTime.restype=None

def current_boot_filetime():
    """Query and validate the local Windows boot time in process FILETIME units."""
    command="(Get-CimInstance Win32_OperatingSystem -ErrorAction Stop).LastBootUpTime.ToFileTimeUtc()"
    result=subprocess.run(['powershell','-NoProfile','-NonInteractive','-Command',command],check=True,
                          capture_output=True,text=True,timeout=10,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    value=result.stdout.strip()
    current=wintypes.FILETIME()
    k.GetSystemTimeAsFileTime(ctypes.byref(current))
    now=(current.dwHighDateTime<<32)|current.dwLowDateTime
    if not (1<=len(value)<=20 and value.isascii() and value.isdecimal() and 0<int(value)<=now):
        raise ValueError('unverifiable Windows boot FILETIME')
    return int(value)

def process_identity(pid):
    h=k.OpenProcess(0x1000,False,pid)
    if not h:raise ctypes.WinError(ctypes.get_last_error())
    try:
        created,exited,kernel,user=(wintypes.FILETIME() for _ in range(4))
        if not k.GetProcessTimes(h,ctypes.byref(created),ctypes.byref(exited),ctypes.byref(kernel),ctypes.byref(user)):raise ctypes.WinError(ctypes.get_last_error())
        size=wintypes.DWORD(32768);buf=ctypes.create_unicode_buffer(size.value)
        if not k.QueryFullProcessImageNameW(h,0,buf,ctypes.byref(size)):raise ctypes.WinError(ctypes.get_last_error())
        return {'pid':pid,'creation_filetime':(created.dwHighDateTime<<32)|created.dwLowDateTime,'image':str(Path(buf.value).resolve())}
    finally:k.CloseHandle(h)
