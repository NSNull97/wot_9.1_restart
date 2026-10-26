"""GW-01 synthetic native-login load against an own loopback stand copy.

`prepare` copies only durable state (SQLite via the backup API, fixtures) of
a stopped-or-running source stand into a FRESH directory, gives it its own
ports, identity token and gateway executable, removes the Domain flag and
sets `connection_capacity`; battle resources stay pinned read-only where the
source stand pins them. Nothing of the source stand is modified.

`accounts` adds N disposable test accounts to the copy only (web.sqlite rows
with the site's scrypt format, bridge service lists); passwords are written
to `gw01-accounts.json` in the copy and never printed.

OBSERVED 2026-10-26: the profile13 bridge starts only when every listed owner
(at most 6, web/src/p08b-battle.mjs) is a fully provisioned P08B owner; a fresh
account fails worker activation with OWNER_SOURCE_REQUIRED. `run` therefore
needs provisioned accounts in `gw01-accounts.json`; `accounts` alone is not enough.

`run` drives real native 0.9.1 LoginRequests (RSA-OAEP with the stand key),
the BaseApp handshake, the first channel message and the native disconnect
`[11,0]`. Loopback only. It records reply codes, latencies and the gateway's
working set / CPU time. A synthetic client proves gateway capacity, not
native UI, sound or battle (AGENTS).
"""
import argparse
import ctypes
import hashlib
import json
import os
import secrets
import shutil
import socket
import sqlite3
import struct
import threading
import time
import uuid
from ctypes import wintypes
from datetime import datetime, timezone
from pathlib import Path

from cryptography.hazmat.decrepit.ciphers.algorithms import Blowfish
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.ciphers import Cipher, modes

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = 0x02030000
MAGIC = struct.pack('<I', 0xDEADBEEF)
LOOPBACK = '127.0.0.1'
# Bridge limits (web/src/game-adapter.mjs): 60 logins/min per process, 10 per
# e-mail per 15 min; 2 concurrent scrypt checks (web/src/security.mjs).
LOGINS_PER_MINUTE = 55
PER_ACCOUNT_LOGINS = 9
WINDOW_S = 15 * 60 + 30
SERVICE_LISTS = ('battle_service', 'pool_service', 'mixed_service', 'ammo_loss_service')
# web/src/p08b-battle.mjs and siblings: every configured owner list holds 1..6 accounts.
MAX_LISTED_OWNERS = 6


def now_utc():
    return datetime.now(timezone.utc).isoformat()


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def loopback_port(value):
    host, port = value.rsplit(':', 1)
    if host != LOOPBACK or not 0 < int(port) < 65536:
        raise ValueError('loopback endpoint required')
    return host, int(port)


def backup(source, target):
    src = sqlite3.connect(f'file:{Path(source).as_posix()}?mode=ro', uri=True)
    dst = sqlite3.connect(target)
    try:
        src.backup(dst)
        if dst.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise ValueError(f'{target} integrity')
    finally:
        dst.close(); src.close()


def prepare(args):
    source = Path(args.source_stand).resolve(strict=True)
    out = Path(args.out).resolve()
    if out.exists():
        raise ValueError('fresh output directory required')
    gateway_exe = Path(args.gateway).resolve(strict=True)
    configs = {n: json.loads((source / n).read_text(encoding='utf-8')) for n in ('gateway.json', 'bridge.json')}
    gw, br = configs['gateway.json'], configs['bridge.json']
    local_root = Path(gw['local_root']).resolve()
    if not out.is_relative_to(local_root / 'stands'):
        raise ValueError('the gateway accepts captures only below its local_root; use <local_root>/stands/<fresh>')
    login, base, identity = args.ports
    out.mkdir(parents=True)
    for name in ('game.sqlite', 'web.sqlite'):
        backup(source / name, out / name)
    shutil.copytree(source / 'fixtures', out / 'fixtures')
    (out / 'identity.token').write_text(secrets.token_urlsafe(32), encoding='ascii')
    gw.update(login_bind=f'{LOOPBACK}:{login}', base_bind=f'{LOOPBACK}:{base}', identity_endpoint=f'{LOOPBACK}:{identity}',
              identity_token_file=str(out / 'identity.token'), connection_capacity=args.capacity)
    gw.pop('domain_service', None)
    if args.capacity is None:
        gw.pop('connection_capacity')
    br.update(port=identity, token_file=str(out / 'identity.token'), fixture_root=str(out / 'fixtures'),
              game_database=str(out / 'game.sqlite'), web_database=str(out / 'web.sqlite'))
    br.pop('domain_service', None)
    for name, value in configs.items():
        (out / name).write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    # Battle resources stay pinned where the source stand pins them (read-only).
    shutil.copy2(source / 'battle-profiles.json', out / 'battle-profiles.json')
    receipt = dict(schema='wot091-gw01-load-stand.v1', created_utc=now_utc(), source_stand=str(source),
                   gateway=dict(path=str(gateway_exe), sha256=sha(gateway_exe)), checkout=str(ROOT), bridge_checkout=str(local_root.parent),
                   ports=dict(login=login, base=base, identity=identity), connection_capacity=args.capacity,
                   battle_profiles_sha256=sha(out / 'battle-profiles.json'), domain_service=False, native='NOT_RUN')
    (out / 'stand-receipt.json').write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
    # The bridge accepts a config only below its own checkout's local/.
    services = SERVICES.replace('__ROOT__', str(local_root.parent)).replace('__STAND__', str(out)) \
        .replace('__GATEWAY__', str(gateway_exe)).replace('__LOCAL__', str(local_root))
    (out / 'services.ps1').write_text(services, encoding='utf-8')
    print(json.dumps(receipt, indent=2))


SERVICES = r'''param([ValidateSet('start','stop')][string]$Action)
# Generated by tools/gw01_login_load.py: bridge and tools from __ROOT__, no Domain.
$ErrorActionPreference = 'Stop'
$root = '__ROOT__'; $stand = '__STAND__'; $gatewayExe = '__GATEWAY__'; $local = '__LOCAL__'
$order = if ($Action -eq 'start') { @('bridge','gateway') } else { @('gateway','bridge') }
foreach ($kind in $order) {
  $record = Join-Path $stand ($kind + '-process.json')
  if ($Action -eq 'stop') {
    if (-not (Test-Path $record)) { Write-Output "$kind not started"; continue }
    $r = Get-Content $record -Raw | ConvertFrom-Json
    $p = Get-CimInstance Win32_Process -Filter ("ProcessId=" + $r.pid)
    if ($p -and $p.ExecutablePath -eq $r.exe -and $p.CommandLine.Contains($r.config)) { Stop-Process -Id $r.pid; Wait-Process -Id $r.pid -Timeout 10 -ErrorAction SilentlyContinue; Write-Output "$kind stopped: $($r.pid)" }
    else { Write-Output "$kind already absent or not ours: $($r.pid)" }
    Rename-Item $record ($kind + '-process-' + (Get-Date -Format 'HHmmss') + '.json')
    continue
  }
  if (Test-Path $record) { throw "$kind already has a live receipt" }
  $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
  if ($kind -eq 'bridge') {
    $config = Join-Path $stand 'bridge.json'
    $exe = (Get-Command node).Source; $args = @('server/identity/service.mjs','--config',$config)
  } else {
    $config = Join-Path $stand 'gateway.json'
    $exe = $gatewayExe
    $env:WOT091_STAB_DIAGNOSTICS_DIR = Join-Path $stand ('cadence-' + $stamp)
    New-Item -ItemType Directory -Force $env:WOT091_STAB_DIAGNOSTICS_DIR | Out-Null
    $args = @('legacy091-profile13',(Join-Path $local 'server\native-private.pem'),(Join-Path $local 'server\client-digest.bin'),
      $config,(Join-Path $stand 'battle-profiles.json'),(Join-Path $stand ('capture-' + $stamp)))
  }
  $out = Join-Path $stand ($kind + '-' + $stamp + '.stdout.log'); $err = Join-Path $stand ($kind + '-' + $stamp + '.stderr.log')
  $p = Start-Process -FilePath $exe -ArgumentList $args -WorkingDirectory $root -RedirectStandardOutput $out -RedirectStandardError $err -WindowStyle Hidden -PassThru
  @{pid=$p.Id;kind=$kind;exe=$exe;exe_sha256=(Get-FileHash $exe -Algorithm SHA256).Hash.ToLower();config=$config;stdout=$out;stderr=$err;started_utc=[DateTime]::UtcNow.ToString('o')} | ConvertTo-Json | Set-Content $record -Encoding utf8
  Start-Sleep -Seconds 5; $p.Refresh()
  if ($p.HasExited) { Get-Content $err; throw "$kind exited at startup" }
  Write-Output "$kind started: $($p.Id)"; Get-Content $out | Select-Object -Last 3
}
'''


def scrypt_record(password):
    salt = secrets.token_hex(16)
    key = hashlib.scrypt(password.encode(), salt=salt.encode(), n=131072, r=8, p=1, maxmem=192 * 1024 * 1024, dklen=64)
    return f'scrypt$v1$131072$8$1${salt}${key.hex()}'


def ensure_game_profile(db, account_id, nickname, created_at):
    """Same row as `game.ensure` (web/src/game-adapter.mjs) on a first login; the
    bridge requires configured owners to have it before it starts."""
    native_id = db.execute("INSERT INTO game_profiles(account_id,profile_json) VALUES (?,'{}')", (account_id,)).lastrowid
    value = dict(profile_version=1, account_id=account_id, username=nickname, native_database_id=native_id,
                 created_at_ms=created_at, snapshot_revision=1, resources=dict(credits=100000, gold=0, free_xp=0),
                 statistics=dict(battles=0, wins=0, losses=0, draws=0))
    db.execute('UPDATE game_profiles SET profile_json=? WHERE account_id=?', (json.dumps(value, separators=(',', ':')), account_id))


OWNER_TABLES = ('game_meta', 'game_profiles', 'game_limits')


def worker(checkout, bridge, stand, account_id, operation, request=None, *, mixed=False, loss=False):
    """One call of the bridge's own worker CLI (web/src/p04d-crew.mjs `run`) against the copy."""
    import subprocess
    ammo = bridge['ammunition_service']
    argv = [bridge['python_executable'], '-B', '-X', 'utf8', str(checkout / 'tools/p08b_battle_service.py'),
            '--database', str(stand / 'game.sqlite'), '--bundle', ammo['bundle_root'], '--original-root', ammo['original_root'],
            '--account-id', account_id, '--fixture-root', str(stand / 'fixtures')]
    if mixed:
        argv += ['--mixed-ammo', '--shell-catalog', bridge['mixed_service']['shell_catalog'],
                 '--terminal-policy', bridge['mixed_service']['terminal_policy']]
        if 'catalog' in bridge:
            argv += ['--catalog-sha256', bridge['catalog']['sha256']]
    if loss:
        argv.append('--ammo-rack-loss')
    argv.append(operation)
    done = subprocess.run(argv, cwd=checkout, input=json.dumps(request).encode() if request else b'', capture_output=True, timeout=300)
    if done.returncode != 0:
        raise ValueError(f'{operation} {account_id[:8]}: ' + done.stderr.decode(errors='replace').strip().splitlines()[-1])
    return json.loads(done.stdout)


def owners(args):
    """Synthetic owners through the project's own P08B chain, then the bridge worker
    activations; the copy's bridge/gateway owner lists then name only them (<= 6).

    `p08b_owner_source.py stage` builds a one-owner P08B DB per account from a
    one-owner legacy DB (native id k, so ids never collide), and
    `p08b_owner_onboard.py` imports owners 2..N into a copy of stage 1. Both only
    accept paths below the bridge checkout's local/evidence/20261015-p08b-01, where
    this writes one NEW dir. Pool/mixed/loss activations then run on the stand copy."""
    import shutil as _shutil
    import subprocess
    import sys
    stand = Path(args.stand).resolve(strict=True)
    if not stopped(stand) or (stand / 'gw01-owners.json').exists():
        raise ValueError('stopped stand without owners required')
    bridge = json.loads((stand / 'bridge.json').read_text(encoding='utf-8'))
    checkout = Path(bridge['game_database']).resolve().parents[3]
    sys.path[:0] = [str(checkout / 'tools'), str(checkout)]
    from p08b_owner_source import EVIDENCE
    from p06t_mixed_store import POLICY_SHA256 as MIXED_SHA, SOURCE_SHA256
    from p06t_terminal import MANIFEST_SHA256
    from p06t_ammo_loss_store import CONTRACT as LOSS_CONTRACT, POLICY_SHA256 as LOSS_SHA
    rows = json.loads((stand / 'gw01-accounts.json').read_text(encoding='utf-8'))['accounts']
    ammo = bridge['ammunition_service']
    work = EVIDENCE / f'gw01-{stand.name}'
    target = work / 'owners' / 'game.sqlite'
    # Resume only a complete earlier staging of this same stand (all receipts present).
    resume = work.exists()
    if resume and not (target.is_file() and all((work / f'stage-{k}' / 'receipt.json').is_file() for k in range(1, len(rows) + 1))
                       and all((work / f'onboard-{k}.json').is_file() for k in range(2, len(rows) + 1))):
        raise ValueError(f'{work} exists but is incomplete; only new evidence dirs are written')
    work.mkdir(parents=True, exist_ok=True)

    def tool(script, *argv):
        done = subprocess.run([bridge['python_executable'], '-B', '-X', 'utf8', str(checkout / 'tools' / script), *argv],
                              cwd=checkout, capture_output=True, timeout=600)
        if done.returncode != 0:
            raise ValueError(f'{script}: ' + done.stderr.decode(errors='replace').strip().splitlines()[-1])
        return json.loads(done.stdout)

    src = sqlite3.connect(f'file:{(stand / "game.sqlite").as_posix()}?mode=ro', uri=True)
    ddl = {n: src.execute("SELECT sql FROM sqlite_master WHERE name=?", (n,)).fetchone()[0] for n in OWNER_TABLES}
    meta = src.execute('SELECT * FROM game_meta').fetchall()
    src.close()
    web = sqlite3.connect(f'file:{(stand / "web.sqlite").as_posix()}?mode=ro', uri=True)
    stages = []
    for native_id, row in enumerate(rows, 1):
        if resume:
            stages.append(json.loads((work / f'stage-{native_id}' / 'receipt.json').read_text(encoding='ascii')))
            continue
        legacy = work / f'legacy-{native_id}.sqlite'
        with sqlite3.connect(legacy) as db:
            for name in OWNER_TABLES:
                db.execute(ddl[name])
            db.execute('PRAGMA user_version=1')  # as web/src/game-adapter.mjs openGameStore
            db.executemany(f'INSERT INTO game_meta VALUES ({",".join("?" * len(meta[0]))})', meta)
            created = web.execute('SELECT created_at FROM users WHERE id=?', (row['account_id'],)).fetchone()[0]
            value = dict(profile_version=1, account_id=row['account_id'], username=row['nickname'], native_database_id=native_id,
                         created_at_ms=created, snapshot_revision=1, resources=dict(credits=100000, gold=0, free_xp=0),
                         statistics=dict(battles=0, wins=0, losses=0, draws=0))
            db.execute('INSERT INTO game_profiles(native_id,account_id,profile_json) VALUES (?,?,?)',
                       (native_id, row['account_id'], json.dumps(value, separators=(',', ':'))))
        db.close()
        out = work / f'stage-{native_id}'
        stages.append(tool('p08b_owner_source.py', 'stage', '--database', str(legacy), '--identity-database', str(stand / 'web.sqlite'),
                           '--account-id', row['account_id'], '--anchor-bundle', ammo['bundle_root'], '--original-root', ammo['original_root'],
                           '--out', str(out), '--granted-at-ms', str(created + 1000)))
    web.close()
    if not resume:
        target.parent.mkdir()
        backup(work / 'stage-1' / 'game.sqlite', target)
    onboarded = [json.loads((work / f'onboard-{k}.json').read_text(encoding='ascii')) for k in range(2, len(rows) + 1)] if resume else [tool('p08b_owner_onboard.py', '--database', str(target), '--stage-database', str(work / f'stage-{k}' / 'game.sqlite'),
                      '--anchor-bundle', ammo['bundle_root'], '--original-root', ammo['original_root'],
                      '--account-id', row['account_id'], '--receipt', str(work / f'onboard-{k}.json'))
                 for k, row in enumerate(rows, 1) if k > 1]
    # The copy now runs on the synthetic owners only; the source-stand copy stays beside it.
    (stand / 'game.sqlite').rename(stand / 'game.source-copy.sqlite')
    for suffix in ('-wal', '-shm'):
        if (stand / f'game.sqlite{suffix}').exists():
            (stand / f'game.sqlite{suffix}').rename(stand / f'game.source-copy.sqlite{suffix}')
    backup(target, stand / 'game.sqlite')
    owned = [dict(account_id=r['account_id'], native_id=k) for k, r in enumerate(rows, 1)]
    # Bridge worker activations, step-major in the order its flags require.
    for o in owned:
        worker(checkout, bridge, stand, o['account_id'], 'activate')
    for o in owned:
        pool = worker(checkout, bridge, stand, o['account_id'], 'pool-overview')
        revision = worker(checkout, bridge, stand, o['account_id'], 'overview')['revision']
        worker(checkout, bridge, stand, o['account_id'], 'pool-activate', dict(version=1, account_id=o['account_id'], native_database_id=o['native_id'],
               command_key='gw01-pool-activate', expected_revision=revision, definition_sha256=pool['definition_sha256'],
               registry_sha256=pool['registry_sha256']))
    for o in owned:
        revision = worker(checkout, bridge, stand, o['account_id'], 'overview')['revision']
        worker(checkout, bridge, stand, o['account_id'], 'mixed-activate', dict(version=2, account_id=o['account_id'], native_database_id=o['native_id'],
               expected_revision=revision, policy_sha256=MIXED_SHA, shell_catalog_sha256=SOURCE_SHA256,
               terminal_policy_sha256=MANIFEST_SHA256), mixed=True)
    for o in owned:
        revision = worker(checkout, bridge, stand, o['account_id'], 'mixed-overview', mixed=True)['revision']
        worker(checkout, bridge, stand, o['account_id'], 'loss-activate', dict(version=4, contract=LOSS_CONTRACT, account_id=o['account_id'],
               native_database_id=o['native_id'], expected_revision=revision, policy_sha256=LOSS_SHA), mixed=True, loss=True)
    receipts = [dict(schema='wot091-gw01-owner.v1', account_id=o['account_id'], native_database_id=o['native_id'],
                     stage=str(work / f"stage-{o['native_id']}"), source_sha256=s['source_sha256'],
                     onboard=None if o['native_id'] == 1 else onboarded[o['native_id'] - 2]['status'],
                     activations=['activate', 'pool-activate', 'mixed-activate', 'loss-activate'])
                for o, s in zip(owned, stages)]
    ids = [r['account_id'] for r in rows]
    for name in (*SERVICE_LISTS, 'late_result_service'):
        if name in bridge:
            bridge[name]['accounts'] = list(ids)
    bridge['ammunition_service']['account_id'] = ids[0]
    (stand / 'bridge.json').write_text(json.dumps(bridge, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    gateway = json.loads((stand / 'gateway.json').read_text(encoding='utf-8'))
    if gateway.get('p08c_late_results'):
        gateway['p08c_late_results_accounts'] = list(ids)
    (stand / 'gateway.json').write_text(json.dumps(gateway, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    (stand / 'gw01-owners.json').write_text(json.dumps(receipts, indent=1) + '\n', encoding='utf-8')
    print(json.dumps([dict(account=r['account_id'][:8], native_id=r['native_database_id'], onboard=r['onboard']) for r in receipts]))


def stopped(stand):
    return not any((stand / f'{k}-process.json').exists() for k in ('bridge', 'gateway'))


def accounts(args):
    """Website rows for N disposable accounts in the copy (game rows come from `owners`)."""
    stand = Path(args.stand).resolve(strict=True)
    if not (stand / 'stand-receipt.json').is_file() or json.loads((stand / 'stand-receipt.json').read_text())['schema'] != 'wot091-gw01-load-stand.v1':
        raise ValueError('only a stand made by this tool')
    if not stopped(stand) or (stand / 'gw01-accounts.json').exists():
        raise ValueError('stopped stand without accounts required')
    if not 1 <= args.count <= MAX_LISTED_OWNERS:
        raise ValueError(f'the bridge lists at most {MAX_LISTED_OWNERS} owners')
    rows, stamp = [], int(time.time() * 1000)
    db = sqlite3.connect(stand / 'web.sqlite')
    try:
        with db:
            for index in range(args.count):
                nick = f'gw01load{index:03d}'
                email = f'{nick}@example.test'
                password = secrets.token_urlsafe(24)
                account_id = str(uuid.uuid4())
                db.execute('INSERT INTO users (id, username, display_nickname, email, display_name, password_hash, created_at, updated_at, last_login_at) '
                           'VALUES (?,?,?,?,?,?,?,?,?)', (account_id, nick, nick, email, nick, scrypt_record(password), stamp, stamp, stamp))
                rows.append(dict(account_id=account_id, nickname=nick, email=email, password=password))
    finally:
        db.close()
    (stand / 'gw01-accounts.json').write_text(json.dumps(dict(schema='wot091-gw01-accounts.v1', accounts=rows)) + '\n', encoding='utf-8')
    print(json.dumps(dict(added=len(rows))))


# --- native wire -----------------------------------------------------------

def bf_encrypt(key, clear):
    ecb = Cipher(Blowfish(key), modes.ECB()).encryptor()
    out, previous = bytearray(), bytes(8)
    for i in range(0, len(clear), 8):
        block = clear[i:i + 8]
        out += ecb.update(bytes(a ^ b for a, b in zip(block, previous)))
        previous = block
    return bytes(out)


def bf_decrypt(key, wire):
    ecb = Cipher(Blowfish(key), modes.ECB()).decryptor()
    out, previous = bytearray(), bytes(8)
    for i in range(0, len(wire), 8):
        block = bytes(a ^ b for a, b in zip(ecb.update(wire[i:i + 8]), previous))
        out += block; previous = block
    return bytes(out)


def channel_encrypt(key, clear):
    pad = (8 - (len(clear) + 5) % 8) % 8
    return bf_encrypt(key, clear + bytes(pad) + MAGIC + bytes([pad + 1]))


def channel_decrypt(key, wire):
    if len(wire) % 8 or len(wire) > 1024:
        raise ValueError('encrypted size')
    clear = bf_decrypt(key, wire)
    waste = clear[-1]
    if clear[-5:-1] != MAGIC or not 1 <= waste <= 8:
        raise ValueError('channel footer')
    return clear[:len(clear) - 4 - waste]


def blob(data):
    if len(data) >= 255:
        return bytes([255]) + len(data).to_bytes(3, 'little') + data
    return bytes([len(data)]) + data


def login_request(public_key, request_id, email, password, session_key, digest, nonce):
    username = json.dumps({'login': email, 'auth_method': 'basic', 'session': secrets.token_hex(16),
                           'auth_realm': 'RU', 'game': 'wot', 'temporary': '1'}, separators=(',', ':')).encode()
    plain = b'\x01' + blob(username) + blob(password.encode()) + b'\x10' + session_key + digest + struct.pack('<I', nonce)
    oaep = padding.OAEP(mgf=padding.MGF1(hashes.SHA1()), algorithm=hashes.SHA1(), label=None)
    cipher = b''.join(public_key.encrypt(plain[i:i + 86], oaep) for i in range(0, len(plain), 86))
    body = struct.pack('<I', PROTOCOL) + cipher
    return bytes([1, 0, 0]) + struct.pack('<HI', len(body), request_id) + b'\x00\x00' + body + b'\x02\x00'


def parse_reply(data, request_id):
    """Native LoginReply: [flags2][0xff][u32 length][u32 request][status ...]."""
    if len(data) < 12 or data[2] != 0xFF:
        raise ValueError('not a reply element')
    length, rid = struct.unpack_from('<II', data, 3)
    if rid != request_id:
        raise ValueError('foreign request id')
    return data[11:7 + length]


def frame(token, payload, sequence):
    # Measured native first message: flags 0x0458, [1, token, ...], sequence, cumulative 0.
    return b'\x58\x04' + b'\x01' + struct.pack('<I', token) + payload + struct.pack('<II', sequence, 0)


class Cycle:
    def __init__(self, ctx, account, index):
        self.ctx, self.account, self.index = ctx, account, index
        self.row = dict(index=index, account=account['account_id'][:8], code=None, phase='login')

    def login(self):
        ctx, row = self.ctx, self.row
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind((LOOPBACK, 0))
        self.key = secrets.token_bytes(16)
        request_id = secrets.randbits(31) or 1
        wire = login_request(ctx.public_key, request_id, self.account['email'], self.account['password'],
                             self.key, ctx.digest, secrets.randbits(32))
        started = time.perf_counter(); row['started'] = time.time()
        deadline, resend = started + ctx.reply_timeout, started
        while True:
            now = time.perf_counter()
            if now >= deadline:
                row.update(code='timeout', phase='login'); return False
            if now >= resend:
                self.sock.sendto(wire, ctx.login); resend = now + 3.0
            self.sock.settimeout(max(0.05, min(resend, deadline) - now))
            try:
                data, peer = self.sock.recvfrom(2048)
            except socket.timeout:
                continue
            if peer != ctx.login:
                continue
            payload = parse_reply(data, request_id)
            row['login_ms'] = round((time.perf_counter() - started) * 1000, 1)
            row['code'] = payload[0]
            if payload[0] != 1:
                return False
            clear = bf_decrypt(self.key, payload[1:17])
            self.base = (socket.inet_ntoa(clear[0:4]), struct.unpack_from('>H', clear, 4)[0])
            self.login_key = struct.unpack_from('<I', clear, 8)[0]
            return True

    def handshake(self):
        ctx, row = self.ctx, self.row
        row['phase'] = 'base'
        if self.base != ctx.base:
            raise ValueError(f'redirect to an unexpected base {self.base}')
        request_id = secrets.randbits(31) or 1
        request = bytes([1, 0, 0, 8, 0]) + struct.pack('<I', request_id) + b'\x00\x00' + struct.pack('<II', self.login_key, 0) + b'\x02\x00'
        started = time.perf_counter()
        self.sock.sendto(request, ctx.base)
        self.sock.settimeout(ctx.reply_timeout)
        while True:
            data, peer = self.sock.recvfrom(2048)
            if peer != ctx.base:
                continue
            clear = channel_decrypt(self.key, data)
            if clear[:3] != b'\x00\x00\xff' or struct.unpack_from('<I', clear, 7)[0] != request_id:
                continue
            self.token = struct.unpack_from('<I', clear, 11)[0]
            break
        self.sock.sendto(channel_encrypt(self.key, frame(self.token, b'\x09', 0)), ctx.base)
        row['base_ms'] = round((time.perf_counter() - started) * 1000, 1)
        row['phase'] = 'hangar'

    def drain(self):
        self.sock.settimeout(0.0)
        try:
            while True:
                self.sock.recvfrom(2048)
        except (BlockingIOError, socket.timeout):
            pass

    def disconnect(self):
        self.drain()
        self.sock.sendto(channel_encrypt(self.key, frame(self.token, b'\x0b\x00', 1)), self.ctx.base)
        self.row['phase'] = 'disconnected'; self.row['ended'] = time.time()
        self.sock.close()


class Pacer:
    def __init__(self, per_minute):
        self.interval, self.next, self.lock = 60.0 / per_minute, time.perf_counter(), threading.Lock()

    def wait(self):
        with self.lock:
            delay = self.next - time.perf_counter()
            self.next = max(self.next, time.perf_counter()) + self.interval
        if delay > 0:
            time.sleep(delay)


class ProcessSampler(threading.Thread):
    class COUNTERS(ctypes.Structure):
        _fields_ = [('cb', wintypes.DWORD), ('PageFaultCount', wintypes.DWORD), ('PeakWorkingSetSize', ctypes.c_size_t),
                    ('WorkingSetSize', ctypes.c_size_t), ('QuotaPeakPagedPoolUsage', ctypes.c_size_t),
                    ('QuotaPagedPoolUsage', ctypes.c_size_t), ('QuotaPeakNonPagedPoolUsage', ctypes.c_size_t),
                    ('QuotaNonPagedPoolUsage', ctypes.c_size_t), ('PagefileUsage', ctypes.c_size_t),
                    ('PeakPagefileUsage', ctypes.c_size_t), ('PrivateUsage', ctypes.c_size_t)]

    def __init__(self, pid, period):
        super().__init__(daemon=True)
        self.pid, self.period, self.samples, self.stop = pid, period, [], threading.Event()
        k32 = ctypes.WinDLL('kernel32', use_last_error=True)
        self.k32, self.psapi = k32, ctypes.WinDLL('psapi', use_last_error=True)
        self.handle = k32.OpenProcess(0x1000 | 0x0010, False, pid)  # QUERY_LIMITED_INFORMATION | VM_READ
        if not self.handle:
            raise OSError(ctypes.get_last_error(), 'OpenProcess gateway')

    def sample(self):
        c = self.COUNTERS(); c.cb = ctypes.sizeof(c)
        if not self.psapi.GetProcessMemoryInfo(self.handle, ctypes.byref(c), c.cb):
            raise OSError(ctypes.get_last_error(), 'GetProcessMemoryInfo')
        t = [wintypes.FILETIME() for _ in range(4)]
        if not self.k32.GetProcessTimes(self.handle, *[ctypes.byref(x) for x in t]):
            raise OSError(ctypes.get_last_error(), 'GetProcessTimes')
        cpu = sum((x.dwHighDateTime << 32 | x.dwLowDateTime) for x in t[2:]) / 1e7
        return dict(t=time.time(), working_set=c.WorkingSetSize, private=c.PrivateUsage, cpu_s=cpu)

    def run(self):
        while not self.stop.is_set():
            self.samples.append(self.sample()); self.stop.wait(self.period)


class Context:
    pass


def run(args):
    stand = Path(args.stand).resolve(strict=True)
    gateway = json.loads((stand / 'gateway.json').read_text(encoding='utf-8'))
    ctx = Context()
    ctx.login, ctx.base = loopback_port(gateway['login_bind']), loopback_port(gateway['base_bind'])
    ctx.reply_timeout = args.reply_timeout
    local = Path(gateway['local_root'])
    private = serialization.load_pem_private_key((local / 'server/native-private.pem').read_bytes(), password=None)
    ctx.public_key = private.public_key(); del private
    ctx.digest = (local / 'server/client-digest.bin').read_bytes()
    pool = json.loads((stand / 'gw01-accounts.json').read_text(encoding='utf-8'))['accounts']
    record = json.loads((stand / 'gateway-process.json').read_text(encoding='utf-8-sig'))
    sampler = ProcessSampler(record['pid'], args.sample_period); before = sampler.sample(); sampler.start()
    pacer, rows, lock = Pacer(args.per_minute), [], threading.Condition()
    # Per e-mail: at most PER_ACCOUNT_LOGINS starts in any bridge window, one live session.
    starts = {a['account_id']: [] for a in pool}; busy = set()
    out = Path(args.evidence).resolve(); out.mkdir(parents=True, exist_ok=False)
    started = time.time()

    def take(index):
        with lock:
            while True:
                now = time.time()
                free = [a for a in pool if a['account_id'] not in busy
                        and sum(now - t < WINDOW_S for t in starts[a['account_id']]) < PER_ACCOUNT_LOGINS]
                if free:
                    account = min(free, key=lambda a: len(starts[a['account_id']]))
                    starts[account['account_id']].append(now); busy.add(account['account_id'])
                    return Cycle(ctx, account, index)
                lock.wait(timeout=5.0)

    def release(cycle):
        with lock:
            busy.discard(cycle.account['account_id']); lock.notify_all()

    def attempt(cycle, hold):
        pacer.wait()
        try:
            if cycle.login():
                cycle.handshake()
                if hold:
                    return cycle
                time.sleep(args.dwell)
                cycle.disconnect()
                time.sleep(args.dwell)  # let the gateway retire the session before the account is reused
        except Exception as error:  # recorded as a failed cycle, never as success
            cycle.row.update(error=f'{type(error).__name__}: {error}')
        finally:
            with lock:
                rows.append(cycle.row)
            if not hold:
                release(cycle)
        return None

    # Phase 1: hold `concurrent` hangar sessions at once (distinct accounts), then disconnect all.
    held, threads = [], []
    hold_n = min(args.concurrent, len(pool), args.cycles)
    hold_cycles = [take(i) for i in range(hold_n)]
    sem = threading.Semaphore(args.parallel)

    def hold_worker(c):
        with sem:
            if attempt(c, True):
                with lock:
                    held.append(c)
    for c in hold_cycles:
        t = threading.Thread(target=hold_worker, args=(c,)); t.start(); threads.append(t)
    for t in threads:
        t.join()
    peak = dict(held=len(held), at=time.time(), process=sampler.sample())
    time.sleep(args.hold)
    for c in held:
        try:
            c.disconnect()
        except Exception as error:
            c.row.update(error=f'disconnect {type(error).__name__}: {error}')
    time.sleep(args.dwell)
    for c in hold_cycles:
        release(c)
    # Phase 2: churn the remaining cycles, `parallel` at a time.
    index = iter(range(hold_n, args.cycles)); threads = []

    def churn():
        while True:
            with lock:
                i = next(index, None)
            if i is None:
                return
            attempt(take(i), False)
    for _ in range(args.parallel):
        t = threading.Thread(target=churn); t.start(); threads.append(t)
    for t in threads:
        t.join()
    time.sleep(2)
    sampler.stop.set(); sampler.join(); after = sampler.sample()
    codes = {}
    for r in rows:
        codes[str(r['code'])] = codes.get(str(r['code']), 0) + 1
    lat = sorted(r['login_ms'] for r in rows if 'login_ms' in r)
    pct = lambda q: lat[min(len(lat) - 1, int(q * len(lat)))] if lat else None
    ws = [s['working_set'] for s in sampler.samples] or [before['working_set']]
    summary = dict(schema='wot091-gw01-login-load.v1', stand=str(stand), started_utc=datetime.fromtimestamp(started, timezone.utc).isoformat(),
                   duration_s=round(time.time() - started, 1), cycles=len(rows), reply_codes=codes,
                   disconnected=sum(r['phase'] == 'disconnected' for r in rows), errors=sum('error' in r for r in rows),
                   login_ms=dict(p50=pct(.5), p95=pct(.95), max=lat[-1] if lat else None),
                   concurrent_hangar_sessions=peak['held'], accounts=len(pool), per_minute=args.per_minute, parallel=args.parallel,
                   gateway=dict(pid=record['pid'], exe_sha256=record.get('exe_sha256'),
                                working_set_mb=dict(before=round(before['working_set'] / 2**20, 1), peak_sampled=round(max(ws) / 2**20, 1),
                                                    at_peak_sessions=round(peak['process']['working_set'] / 2**20, 1),
                                                    after=round(after['working_set'] / 2**20, 1)),
                                private_mb_after=round(after['private'] / 2**20, 1),
                                cpu_s=round(after['cpu_s'] - before['cpu_s'], 2),
                                cpu_percent_of_one_core=round(100 * (after['cpu_s'] - before['cpu_s']) / max(1e-9, after['t'] - before['t']), 1)),
                   classification='OBSERVED synthetic loopback load; native client/UI NOT_RUN')
    (out / 'cycles.json').write_text(json.dumps(sorted(rows, key=lambda r: r['index']), indent=1) + '\n', encoding='utf-8')
    (out / 'process-samples.json').write_text(json.dumps(sampler.samples) + '\n', encoding='utf-8')
    (out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(summary, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('prepare'); p.add_argument('--source-stand', required=True); p.add_argument('--out', required=True)
    p.add_argument('--gateway', required=True); p.add_argument('--capacity', type=int)
    p.add_argument('--ports', type=int, nargs=3, default=(20440, 20441, 3792), metavar=('LOGIN', 'BASE', 'IDENTITY'))
    p.set_defaults(func=prepare)
    p = sub.add_parser('accounts'); p.add_argument('--stand', required=True); p.add_argument('--count', type=int, default=4)
    p.set_defaults(func=accounts)
    p = sub.add_parser('owners'); p.add_argument('--stand', required=True); p.set_defaults(func=owners)
    p = sub.add_parser('run'); p.add_argument('--stand', required=True); p.add_argument('--evidence', required=True)
    p.add_argument('--cycles', type=int, default=200); p.add_argument('--concurrent', type=int, default=4)
    p.add_argument('--parallel', type=int, default=2); p.add_argument('--per-minute', type=int, default=LOGINS_PER_MINUTE)
    p.add_argument('--hold', type=float, default=10.0); p.add_argument('--dwell', type=float, default=1.0)
    p.add_argument('--reply-timeout', type=float, default=25.0); p.add_argument('--sample-period', type=float, default=1.0)
    p.set_defaults(func=run)
    args = parser.parse_args()
    if getattr(args, 'per_minute', 1) > 60 or getattr(args, 'parallel', 1) > 2:
        parser.error('bridge limits: <= 60 logins/min and <= 2 concurrent scrypt checks')
    args.func(args)


if __name__ == '__main__':
    main()
