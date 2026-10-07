"""Extract pinned official CPython 2.7.3 MSI into local/ without running an installer.

Read-only MSI database APIs + SetupIterateCabinetW; no registration or PATH change.
This historical interpreter is only for compiling our own diagnostic module.
"""
import argparse
import ctypes as C
from ctypes import wintypes as W
from pathlib import Path

from client_audit import ROOT, output_dir, save_json, sha256

MSI_SHA256 = '05bf3b9686a64a413eeb6efb03b591f8a6f2d9c5496898f367e9cef79e4b2c02'


def check(code):
    if code:
        raise OSError(code, 'MSI read operation failed')


class Database:
    def __init__(self, path):
        self.api = C.WinDLL('msi')
        for name, args in {
            'MsiOpenDatabaseW': [W.LPCWSTR, W.LPCWSTR, C.POINTER(W.UINT)],
            'MsiDatabaseOpenViewW': [W.UINT, W.LPCWSTR, C.POINTER(W.UINT)],
            'MsiViewExecute': [W.UINT, W.UINT],
            'MsiViewFetch': [W.UINT, C.POINTER(W.UINT)],
            'MsiRecordGetStringW': [W.UINT, W.UINT, W.LPWSTR, C.POINTER(W.DWORD)],
            'MsiRecordReadStream': [W.UINT, W.UINT, C.c_void_p, C.POINTER(W.DWORD)],
            'MsiCloseHandle': [W.UINT],
        }.items():
            fn = getattr(self.api, name)
            fn.argtypes, fn.restype = args, W.UINT
        self.handle = W.UINT()
        check(self.api.MsiOpenDatabaseW(str(path), None, C.byref(self.handle)))

    def rows(self, query, columns, stream=False):
        view = W.UINT()
        check(self.api.MsiDatabaseOpenViewW(self.handle, query, C.byref(view)))
        try:
            check(self.api.MsiViewExecute(view, 0))
            count = 0
            while True:
                record = W.UINT()
                status = self.api.MsiViewFetch(view, C.byref(record))
                if status == 259:
                    break
                check(status)
                try:
                    count += 1
                    if count > 10000:
                        raise ValueError('MSI row limit')
                    row = []
                    for index in range(1, columns + 1):
                        if stream:
                            size = W.DWORD()
                            check(self.api.MsiRecordReadStream(record, index, None, C.byref(size)))
                            if size.value > 32*1024*1024:
                                raise ValueError('MSI stream size limit')
                            buf = C.create_string_buffer(size.value)
                            check(self.api.MsiRecordReadStream(record, index, buf, C.byref(size)))
                            row.append(buf.raw[:size.value])
                        else:
                            size = W.DWORD(2048)
                            buf = C.create_unicode_buffer(size.value)
                            check(self.api.MsiRecordGetStringW(record, index, buf, C.byref(size)))
                            row.append(buf.value)
                    yield row
                finally:
                    check(self.api.MsiCloseHandle(record))
        finally:
            check(self.api.MsiCloseHandle(view))

    def close(self):
        check(self.api.MsiCloseHandle(self.handle))


def extract_cabinet(cab, mapping):
    class FileInfo(C.Structure):
        _fields_ = [('name', W.LPCWSTR), ('size', W.DWORD), ('error', W.DWORD),
                    ('date', W.WORD), ('time', W.WORD), ('attributes', W.WORD),
                    ('target', W.WCHAR*260)]
    class FilePaths(C.Structure):
        _fields_ = [('target', W.LPCWSTR), ('source', W.LPCWSTR),
                    ('error', W.UINT), ('flags', W.DWORD)]
    callback_type = C.WINFUNCTYPE(W.UINT, C.c_void_p, W.UINT, C.c_size_t, C.c_size_t)
    errors = []

    def callback(context, notification, param1, param2):
        try:
            if notification == 0x11:
                info = C.cast(param1, C.POINTER(FileInfo)).contents
                dest, size = mapping[info.name]
                if size != info.size or len(str(dest)) >= 260 or dest.exists():
                    raise ValueError('cabinet target/size collision: '+info.name)
                dest.parent.mkdir(parents=True, exist_ok=True)
                info.target = str(dest)
                return 1
            if notification == 0x13:
                paths = C.cast(param1, C.POINTER(FilePaths)).contents
                if paths.error:
                    raise OSError(paths.error, 'cabinet extraction error')
                return 0
            if notification == 0x12:
                raise ValueError('external cabinet forbidden')
            return 0
        except Exception as error:
            errors.append(repr(error))
            return 0 if notification == 0x11 else 1

    api = C.WinDLL('setupapi', use_last_error=True)
    api.SetupIterateCabinetW.argtypes = [W.LPCWSTR, W.DWORD, callback_type, C.c_void_p]
    api.SetupIterateCabinetW.restype = W.BOOL
    success = api.SetupIterateCabinetW(str(cab), 0, callback_type(callback), None)
    if errors:
        raise RuntimeError(errors)
    if not success:
        raise C.WinError(C.get_last_error())


def extract(msi, target):
    if sha256(msi) != MSI_SHA256:
        raise ValueError('not the pinned official CPython 2.7.3 x86 MSI')
    if any(target.iterdir()):
        raise ValueError('target must be empty')
    db = Database(msi)
    try:
        directories = {a: (b, c) for a, b, c in db.rows('SELECT `Directory`, `Directory_Parent`, `DefaultDir` FROM `Directory`', 3)}
        components = dict(db.rows('SELECT `Component`, `Directory_` FROM `Component`', 2))
        file_rows = list(db.rows('SELECT `File`, `Component_`, `FileName`, `FileSize` FROM `File`', 4))
        cabinets = [r[0] for r in db.rows('SELECT `Cabinet` FROM `Media`', 1)]
        if not 1 <= len(cabinets) <= 8 or not all(c.startswith('#') for c in cabinets):
            raise ValueError('expected bounded embedded cabinets')
        def relative_dir(key, depth=0):
            if depth > 20:
                raise ValueError('directory recursion limit')
            if key in ('TARGETDIR', 'SystemFolder'):
                return Path('.')
            parent, name = directories[key]
            name = name.split(':')[0].split('|')[-1]
            if name in ('', '.'):
                return relative_dir(parent, depth+1)
            return relative_dir(parent, depth+1)/name

        mapping = {}
        for key, component, name, size in file_rows:
            relative = relative_dir(components[component])/name.split('|')[-1]
            dest = (target/relative).resolve()
            if not dest.is_relative_to(target) or dest == target:
                raise ValueError('MSI file path outside output')
            mapping[key] = (dest, int(size))
        for cabinet in cabinets:
            name = cabinet[1:]
            if not name.replace('.', '').replace('_', '').isalnum():
                raise ValueError('unsafe cabinet name')
            stream = list(db.rows("SELECT `Data` FROM `_Streams` WHERE `Name` = '"+name+"'", 1, True))
            if len(stream) != 1:
                raise ValueError('cabinet count mismatch')
            cab = target/(name+'.cab')
            cab.write_bytes(stream[0][0])
            extract_cabinet(cab, mapping)

        manifest = []
        for key, (dest, size) in mapping.items():
            if not dest.is_file() or dest.stat().st_size != size:
                raise ValueError('extracted file mismatch: '+key)
            manifest.append({'path': dest.relative_to(target).as_posix(), 'bytes': size, 'sha256': sha256(dest)})
        save_json(target/'extraction.json', {'url': 'https://www.python.org/ftp/python/2.7.3/python-2.7.3.msi',
            'msi_sha256': MSI_SHA256, 'files': manifest, 'installer_executed': False})
        print({'files': len(manifest), 'target': str(target)})
    finally:
        db.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--msi', required=True)
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    extract((ROOT/args.msi).resolve(strict=True), output_dir(args.out))
