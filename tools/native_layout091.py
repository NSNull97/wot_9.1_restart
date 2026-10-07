"""Read 24 bytes of RPC ranges from our own newly launched, fixed-hash #717 process.

No arbitrary PID/address, no writes/injection or general memory dump. The caller
must pass the Popen object it owns. Header check pins the non-ASLR image base.
"""
import ctypes as C
from ctypes import wintypes as W
import struct
from account_contract_probe import EXE_SHA256
from client_audit import sha256, read_limited


def read_layout(process, exe):
    if process.poll() is not None or sha256(exe) != EXE_SHA256:
        raise ValueError('owned live fixed-hash executable required')
    kernel=C.WinDLL('kernel32',use_last_error=True)
    kernel.ReadProcessMemory.argtypes=[W.HANDLE,C.c_void_p,C.c_void_p,C.c_size_t,C.POINTER(C.c_size_t)]
    kernel.ReadProcessMemory.restype=W.BOOL
    def read(address, size):
        buf=C.create_string_buffer(size);count=C.c_size_t()
        if not kernel.ReadProcessMemory(int(process._handle),address,buf,size,C.byref(count)) or count.value!=size:
            raise C.WinError(C.get_last_error())
        return buf.raw
    if read(0x400000,64)!=read_limited(exe)[:64]:
        raise ValueError('fixed image base/header mismatch')
    rows=[]
    for name,address in [('client_entity_method',0x2305654),('client_entity_property',0x2305660),('base_entity_method',0x230555c)]:
        raw=read(address,8);start,end=struct.unpack('<II',raw)
        if not 0<start<=end<255:raise ValueError('RPC range not initialized')
        rows.append({'name':name,'address':hex(address),'hex':raw.hex(),'start':start,'end':end})
    return {'pid':process.pid,'exe_sha256':EXE_SHA256,'image_base':'0x400000',
            'bytes_read':88,'scope':'read-only own child, header and three RPC ranges','ranges':rows}
