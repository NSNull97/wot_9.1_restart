"""Conservative local supervisor recovery; never signal a recorded PID."""
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import secrets
import time


def utc():
    return datetime.now(timezone.utc).isoformat()


def regular_bytes(path, limit):
    if path.is_symlink() or (hasattr(path, 'is_junction') and path.is_junction()):
        raise ValueError('Linked service record refused')
    if not path.is_file() or path.stat().st_size > limit:
        raise ValueError('Invalid or oversized service record')
    with path.open('rb') as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise ValueError('Service record exceeded limit while reading')
    return data


def probe_pid(pid):
    """ALIVE/ABSENT/UNKNOWN; access denial and PID reuse never mean absent."""
    if type(pid) is not int or not 1 <= pid <= 0xffffffff:
        return {'pid': pid, 'state': 'UNKNOWN', 'reason': 'invalid_pid'}
    if os.name == 'nt':
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.GetExitCodeProcess.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
        kernel.GetExitCodeProcess.restype = wintypes.BOOL
        kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
        kernel.CloseHandle.restype = wintypes.BOOL
        handle = kernel.OpenProcess(0x1000, False, pid)
        if not handle:
            error = ctypes.get_last_error()
            return {'pid': pid, 'state': 'ABSENT' if error == 87 else 'UNKNOWN',
                    'winerror': error}
        try:
            code = wintypes.DWORD()
            if not kernel.GetExitCodeProcess(handle, ctypes.byref(code)):
                return {'pid': pid, 'state': 'UNKNOWN', 'winerror': ctypes.get_last_error()}
            return {'pid': pid, 'state': 'ALIVE' if code.value == 259 else 'ABSENT'}
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return {'pid': pid, 'state': 'ABSENT'}
    except OSError as error:
        return {'pid': pid, 'state': 'UNKNOWN', 'errno': error.errno}
    return {'pid': pid, 'state': 'ALIVE'}


@contextmanager
def lifecycle_guard(directory, timeout=0):
    """OS byte lock releases on process death; the guard file stays in local/."""
    path = directory / 'supervisor.lifecycle'
    if path.is_symlink() or (hasattr(path, 'is_junction') and path.is_junction()):
        raise ValueError('Linked lifecycle guard refused')
    with path.open('a+b') as stream:
        if stream.seek(0, 2) == 0:
            stream.write(b'0')
            stream.flush()
        stream.seek(0)
        deadline = time.monotonic() + timeout
        while True:
            try:
                if os.name == 'nt':
                    import msvcrt
                    msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError as error:
                if time.monotonic() >= deadline:
                    raise RuntimeError('Another service lifecycle operation is in progress') from error
                time.sleep(0.05)
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == 'nt':
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream, fcntl.LOCK_UN)


def snapshot(directory):
    state_path, lock_path = directory / 'state.json', directory / 'supervisor.lock'
    state_raw = regular_bytes(state_path, 16384) if state_path.exists() else None
    state = json.loads(state_raw) if state_raw is not None else {'status': 'NOT_STARTED'}
    if (type(state) is not dict or state.get('status') not in ('NOT_STARTED', 'STARTING', 'RUNNING', 'STOPPED', 'FAILED')
            or type(state.get('processes', [])) is not list or len(state.get('processes', [])) > 8):
        raise ValueError('Invalid bounded supervisor state')
    lock_raw = regular_bytes(lock_path, 64) if lock_path.exists() else None
    lock_pid = None
    if lock_raw is not None:
        text = lock_raw.strip()
        if not text.isdigit() or not 1 <= len(text) <= 10 or not 1 <= int(text) <= 0xffffffff:
            raise ValueError('Invalid supervisor lock PID; preserved')
        lock_pid = int(text)
    rows = []
    if 'supervisor_pid' in state:
        rows.append({'role': 'supervisor', **probe_pid(state['supervisor_pid'])})
    if lock_pid is not None and lock_pid != state.get('supervisor_pid'):
        rows.append({'role': 'lock_owner', **probe_pid(lock_pid)})
    for row in state.get('processes', []):
        if type(row) is not dict:
            raise ValueError('Invalid child process record')
        if row.get('exit_code') is None:
            rows.append({'role': row.get('role', 'child'), **probe_pid(row.get('pid'))})
    return state, state_raw, lock_raw, lock_pid, rows


def observed_status(directory):
    """Do not mutate files or equate saved RUNNING with live processes."""
    try:
        state, _, lock_raw, lock_pid, rows = snapshot(directory)
    except (OSError, ValueError) as error:
        return {'status': 'UNKNOWN', 'observed_utc': utc(), 'observation_error': str(error)}
    result = dict(state)
    result.update(recorded_status=state['status'], observed_utc=utc(),
                  supervisor_lock_present=lock_raw is not None, process_observations=rows)
    if any(row['state'] == 'UNKNOWN' for row in rows):
        result['status'] = 'UNKNOWN'
    elif lock_pid is not None and lock_pid != state.get('supervisor_pid'):
        result['status'] = 'BUSY' if any(row['state'] == 'ALIVE' for row in rows) else 'UNKNOWN'
    elif state['status'] in ('RUNNING', 'STARTING'):
        supervisor = next((row['state'] for row in rows if row['role'] == 'supervisor'), 'UNKNOWN')
        children = [row['state'] for row in rows if row['role'] != 'supervisor']
        if supervisor == 'ABSENT':
            result['status'] = 'ORPHANED' if 'ALIVE' in children else 'STALE'
        elif supervisor == 'UNKNOWN':
            result['status'] = 'UNKNOWN'
        elif lock_raw is None:
            result['status'] = 'INCONSISTENT'
        elif 'ABSENT' in children:
            result['status'] = 'DEGRADED'
    elif any(row['state'] == 'ALIVE' for row in rows):
        result['status'] = 'INCONSISTENT'
    elif lock_raw is not None:
        result['status'] = 'STALE'
    return result


def recover_stale(directory, config_path, preflight):
    """Caller holds lifecycle_guard. Archive only an exactly known dead owner."""
    state, state_raw, lock_raw, lock_pid, rows = snapshot(directory)
    if any(row['state'] != 'ABSENT' for row in rows):
        raise RuntimeError('Service PID is live or unconfirmed; existing state and lock preserved')
    if lock_raw is None and state['status'] not in ('RUNNING', 'STARTING'):
        return None
    if (state_raw is None or state.get('config') != str(config_path)
            or type(state.get('supervisor_pid')) is not int
            or (lock_pid is not None and lock_pid != state['supervisor_pid'])):
        raise RuntimeError('Stale lock does not match known supervisor state; preserved')
    run = Path(state.get('run_dir', '')).resolve(strict=True)
    if run.parent != directory or not run.is_dir() or not run.name.startswith('run-'):
        raise ValueError('Unexpected stale supervisor run directory')
    preflight()
    # Check both bytes and liveness again after possibly slow port checks.
    current = snapshot(directory)
    if current[1:4] != (state_raw, lock_raw, lock_pid) or any(row['state'] != 'ABSENT' for row in current[4]):
        raise RuntimeError('Service state or lock changed during recovery; preserved')
    archive = directory / ('recovery-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S') + '-' + secrets.token_hex(4))
    archive.mkdir()
    (archive / 'state.before.json').write_bytes(state_raw)
    if lock_raw is not None:
        (archive / 'supervisor.lock.before').write_bytes(lock_raw)
    receipt = {'version': 1, 'utc': utc(), 'status': 'RECOVERED_ABSENT_PROCESSES',
               'state_sha256': hashlib.sha256(state_raw).hexdigest(),
               'lock_sha256': hashlib.sha256(lock_raw).hexdigest() if lock_raw is not None else None,
               'process_observations': current[4], 'prior_run_dir': str(run),
               'exit_codes': 'Unknown child exit codes are preserved; no successful exit is invented'}
    prepared = dict(receipt, status='RECOVERY_PREPARED')
    (archive / 'result.json').write_text(json.dumps(prepared, indent=2) + '\n', encoding='utf8')
    # Recheck file bytes immediately before the sole lock mutation.
    if (regular_bytes(directory / 'state.json', 16384) != state_raw
            or (regular_bytes(directory / 'supervisor.lock', 64) if lock_raw is not None else None) != lock_raw):
        raise RuntimeError('Service records changed before archival; preserved')
    if lock_raw is not None:
        (directory / 'supervisor.lock').rename(archive / 'supervisor.lock.retired')
    recovered = dict(state, status='STOPPED', utc=utc(), stop_reason='all_recorded_processes_absent',
                     recovery_receipt=str(archive / 'result.json'))
    temporary = archive / 'state.recovered.json'
    temporary.write_text(json.dumps(recovered, indent=2) + '\n', encoding='utf8')
    os.replace(temporary, directory / 'state.json')
    completed = archive / 'result.completed.json'
    completed.write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf8')
    os.replace(completed, archive / 'result.json')
    return archive / 'result.json'


@contextmanager
def owned_supervisor_lock(directory):
    """Cover early setup exceptions as well as the normal serve cleanup."""
    lock = directory / 'supervisor.lock'
    contents = str(os.getpid()).encode('ascii')
    with lifecycle_guard(directory):
        created = False
        try:
            with lock.open('xb') as stream:
                created = True
                stream.write(contents)
                stream.flush()
        except OSError:
            # The stream is closed and creation guard remains held. An existing
            # owner's record or changed/partial contents are never removed.
            if created and regular_bytes(lock, 64) in (b'', contents):
                lock.unlink()
            raise
    try:
        yield
    finally:
        with lifecycle_guard(directory, timeout=5):
            if regular_bytes(lock, 64) != contents:
                raise RuntimeError('Supervisor lock changed externally; preserved')
            lock.unlink()
