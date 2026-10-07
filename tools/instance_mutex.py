"""Observe the EXE's verified instance mutex; optionally hold our own test mutex.

Never closes, releases, or changes an existing game's handle. Control use creates
an object only when absent, and releases our own handle in finally.
"""
from contextlib import contextmanager
import ctypes as C
from ctypes import wintypes as W

NAME = 'wot_client_mutex'


def api():
    dll = C.WinDLL('kernel32', use_last_error=True)
    dll.OpenMutexW.argtypes = [W.DWORD, W.BOOL, W.LPCWSTR]
    dll.OpenMutexW.restype = W.HANDLE
    dll.CreateMutexW.argtypes = [C.c_void_p, W.BOOL, W.LPCWSTR]
    dll.CreateMutexW.restype = W.HANDLE
    dll.ReleaseMutex.argtypes = [W.HANDLE]
    dll.ReleaseMutex.restype = W.BOOL
    dll.CloseHandle.argtypes = [W.HANDLE]
    dll.CloseHandle.restype = W.BOOL
    return dll


def observe():
    dll = api()
    C.set_last_error(0)
    handle = dll.OpenMutexW(0x100000, False, NAME)
    error = C.get_last_error()
    if handle:
        if not dll.CloseHandle(handle):
            raise C.WinError(C.get_last_error())
        return {'name': NAME, 'exists': True, 'win_error': 0}
    if error != 2:
        raise C.WinError(error)
    return {'name': NAME, 'exists': False, 'win_error': error}


@contextmanager
def control():
    if observe()['exists']:
        raise RuntimeError('another instance mutex exists; control test refused')
    dll = api()
    C.set_last_error(0)
    handle = dll.CreateMutexW(None, True, NAME)
    error = C.get_last_error()
    if not handle:
        raise C.WinError(error)
    if error:
        dll.CloseHandle(handle)
        raise RuntimeError('instance appeared during control setup; refused')
    try:
        yield {'name': NAME, 'created_by_test': True, 'create_error': error}
    finally:
        released = dll.ReleaseMutex(handle)
        closed = dll.CloseHandle(handle)
        if not released or not closed:
            raise RuntimeError('own control mutex release/close failed')
