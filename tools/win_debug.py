"""Bounded Win32 debug events from our own newly created process, without a memory dump.

Layout/API: Microsoft DEBUG_EVENT, OUTPUT_DEBUG_STRING_INFO, WaitForDebugEvent.
Only OutputDebugString's explicitly reported bytes are read from the child.
"""
import ctypes as C
from ctypes import wintypes as W
import struct


class Payload(C.Union):
    _fields_=[('alignment',C.c_uint64),('raw',C.c_ubyte*160)]


class DebugEvent(C.Structure):
    _fields_=[('code',W.DWORD),('pid',W.DWORD),('tid',W.DWORD),('payload',Payload)]


class DebugPump:
    def __init__(self, process):
        if C.sizeof(C.c_void_p)!=8 or C.sizeof(DebugEvent)!=176:
            raise RuntimeError('debug observer requires x64 Python')
        self.process=process
        self.rows=[]
        self.kernel=C.WinDLL('kernel32',use_last_error=True)
        self.kernel.WaitForDebugEvent.argtypes=[C.POINTER(DebugEvent),W.DWORD]
        self.kernel.WaitForDebugEvent.restype=W.BOOL
        self.kernel.ContinueDebugEvent.argtypes=[W.DWORD,W.DWORD,W.DWORD]
        self.kernel.ContinueDebugEvent.restype=W.BOOL
        self.kernel.ReadProcessMemory.argtypes=[W.HANDLE,C.c_void_p,C.c_void_p,C.c_size_t,C.POINTER(C.c_size_t)]
        self.kernel.ReadProcessMemory.restype=W.BOOL
        self.kernel.CloseHandle.argtypes=[W.HANDLE]
        self.kernel.GetFinalPathNameByHandleW.argtypes=[W.HANDLE,W.LPWSTR,W.DWORD,W.DWORD]

    def poll(self):
        for _ in range(100):
            event=DebugEvent()
            if not self.kernel.WaitForDebugEvent(C.byref(event),10):
                error=C.get_last_error()
                if error not in (121,0):
                    raise C.WinError(error)
                return
            if event.pid!=self.process.pid:
                raise RuntimeError('unexpected process in DEBUG_ONLY_THIS_PROCESS')
            raw=bytes(event.payload.raw)
            row={'event':event.code,'pid':event.pid,'tid':event.tid}
            status=0x00010002
            if event.code in (3,6):
                handle=struct.unpack_from('<Q',raw)[0]
                if handle:
                    name=C.create_unicode_buffer(2048)
                    if self.kernel.GetFinalPathNameByHandleW(handle,name,len(name),0):
                        row['module']=name.value
                    self.kernel.CloseHandle(handle)
            elif event.code==1:
                code=struct.unpack_from('<I',raw)[0]
                row.update(exception=hex(code),first_chance=struct.unpack_from('<I',raw,152)[0])
                if code not in (0x80000003,0x4000001f):
                    status=0x80010001
            elif event.code==8:
                addr,unicode_flag,count=struct.unpack_from('<QHH',raw)
                size=min(count*(2 if unicode_flag else 1),4096)
                buf=C.create_string_buffer(size)
                read=C.c_size_t()
                if self.kernel.ReadProcessMemory(int(self.process._handle),addr,buf,size,C.byref(read)):
                    row['text']=buf.raw[:read.value].decode('utf-16-le' if unicode_flag else 'cp1251',errors='replace').rstrip('\0')
                else:
                    row['read_error']=C.get_last_error()
            elif event.code==5:
                row['exit_code']=struct.unpack_from('<I',raw)[0]
            if len(self.rows)>=10000:
                raise RuntimeError('debug event limit')
            self.rows.append(row)
            if not self.kernel.ContinueDebugEvent(event.pid,event.tid,status):
                raise C.WinError(C.get_last_error())
            if event.code==5:
                return
