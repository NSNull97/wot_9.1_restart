import { validateMixedBattleRequest, validateMixedBattleReply } from './p06t-mixed.mjs';
import { validateLossBattleRequest, validateLossBattleReply } from './p06t-ammo-loss.mjs';
/** Separate trusted presentation append. No battle Finish/CAS is performed here. */
import { createHash } from 'node:crypto';
import { spawn } from 'node:child_process';
import { isAbsolute, resolve } from 'node:path';
import { realpathSync, statSync } from 'node:fs';
import { DatabaseSync } from 'node:sqlite';

import { MAX_RESULT_REQUEST } from './p08b-battle.mjs';
export const LATE_CONTRACT = 'p08c-late-result-append.v1';
// RES-30: a seal of 7..30 actors (tools/p08c_late_results.py MAX_SEAL_ROSTER30).
const MAX_SEAL_ROSTER30 = 393216;
export const LATE_POLICY_SHA256 = 'f6ae697fb920b9359a2cb0375aa1fd68538a183fab1c8f136772c703de6abe04';
export const LATE_WORKER_TIMEOUT_MS = 7000;
export const LATE_REQUEST_TIMEOUT_MS = 9000;
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
const SHA = /^[0-9a-f]{64}$/;
const KEY = /^[A-Za-z0-9_:-]{1,96}$/;
const LINK = ['version', 'contract', 'operation', 'account_id', 'native_database_id', 'command_key', 'run_id',
  'battle_id', 'arena_id', 'native_inventory_id', 'reservation_id', 'source_contract', 'frozen_sha256'];
const STAMP = ['source_contract', 'run_id', 'battle_id', 'arena_id', 'reservation_id', 'native_inventory_id',
  'frozen_sha256', 'release_terminal_sha256', 'finished_revision', 'reason'];
const CODES = ['RELEASE_NOT_READY', 'RESULT_MISMATCH', 'LATE_ACTOR_STATE_CHANGED', 'RUN_FENCED', 'FOREIGN_ACCOUNT',
  'DUPLICATE_PAYLOAD_MISMATCH', 'UNSUPPORTED_LATE_RESULTS_SCHEMA', 'INVALID_INPUT'];
const exact = (v, fields) => v && typeof v === 'object' && !Array.isArray(v)
  && Object.keys(v).sort().join(',') === [...fields].sort().join(',');
const integer = (v, lo = 1, hi = 2147483647) => Number.isSafeInteger(v) && v >= lo && v <= hi;
const valid = (ok, message, status) => { if (!ok) throw Object.assign(new Error(`Late result ${message}`), status ? { status } : {}); };
export function canonicalLate(v) {
  return JSON.stringify((function sort(x) {
    if (Array.isArray(x)) return x.map(sort);
    if (x && typeof x === 'object') return Object.fromEntries(Object.keys(x).sort().map(k => [k, sort(x[k])]));
    return x;
  })(v));
}
const bytes = v => Buffer.byteLength(canonicalLate(v));
export const lateHash = v => createHash('sha256').update(canonicalLate(v)).digest('hex');
export function lateConfiguration(v, mixedOwners) {
  valid(exact(v, ['version', 'contract', 'policy_sha256', 'accounts']) && v.version === 1 && v.contract === LATE_CONTRACT
    && v.policy_sha256 === LATE_POLICY_SHA256 && Array.isArray(v.accounts) && v.accounts.length >= 1 && v.accounts.length <= 6
    && Array.isArray(mixedOwners) && v.accounts.every(a => typeof a === 'string' && UUID.test(a) && mixedOwners.includes(a))
    && new Set(v.accounts).size === v.accounts.length, 'explicit owner/policy subset');
  return [...v.accounts];
}
/** Every committed late record needs the new reader, including acked history. */
export function lateReaderFence(database, owners) {
  const db = new DatabaseSync(file(database), { readOnly: true });
  let begun = false;
  try {
    db.exec('PRAGMA query_only=ON; BEGIN'); begun = true;
    const names = db.prepare("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'p08c_late_%' LIMIT 5").all().map(r => r.name).sort();
    if (names.length === 0) return;
    valid(names.join(',') === ['p08c_late_schema', 'p08c_late_seal', 'p08c_late_result', 'p08c_late_command'].sort().join(','), 'reader namespace');
    const marker = db.prepare('SELECT * FROM p08c_late_schema LIMIT 2').all();
    valid(marker.length === 1 && exact(marker[0], ['version', 'policy_sha256', 'catalog_sha256'])
      && marker[0].version === 'p08c-late-results.v1' && marker[0].policy_sha256 === LATE_POLICY_SHA256
      && typeof marker[0].catalog_sha256 === 'string' && SHA.test(marker[0].catalog_sha256), 'reader schema policy');
    const catalog = db.prepare('SELECT catalog_sha256 FROM p09e_schema LIMIT 2').all();
    valid(catalog.length === 1 && catalog[0].catalog_sha256 === marker[0].catalog_sha256, 'reader actual catalog binding');
    const actual = db.prepare('SELECT DISTINCT account_id FROM p08c_late_result LIMIT 7').all().map(r => r.account_id);
    valid(actual.length <= 6 && actual.every(a => typeof a === 'string' && UUID.test(a) && owners.includes(a)), 'reader policy required for committed owners');
  } finally {
    if (begun) db.exec('ROLLBACK');
    db.close();
  }
}
export function validateLateRequest(v, owner) {
  const extra = v?.operation === 'append' ? ['release_terminal_sha256', 'finished_revision', 'seal_json'] : [];
  valid(['release_stamp', 'append'].includes(v?.operation) && exact(v, [...LINK, ...extra])
    && v.version === 1 && v.contract === LATE_CONTRACT && v.account_id === owner && UUID.test(owner)
    && typeof v.run_id === 'string' && UUID.test(v.run_id) && integer(v.native_database_id) && integer(v.native_inventory_id)
    && typeof v.command_key === 'string' && KEY.test(v.command_key) && typeof v.reservation_id === 'string' && KEY.test(v.reservation_id)
    && typeof v.arena_id === 'string' && /^[1-9][0-9]{0,18}$/.test(v.arena_id) && BigInt(v.arena_id) <= 9223372036854775807n
    && v.battle_id === `${v.run_id}:${v.arena_id}` && ['mixed-v2', 'loss-v1'].includes(v.source_contract)
    && typeof v.frozen_sha256 === 'string' && SHA.test(v.frozen_sha256), 'request binding/schema', 400);
  if (extra.length) valid(typeof v.release_terminal_sha256 === 'string' && SHA.test(v.release_terminal_sha256)
    && integer(v.finished_revision, 14) && typeof v.seal_json === 'string' && Buffer.byteLength(v.seal_json) <= MAX_SEAL_ROSTER30, 'bounded immutable seal', 400);
  valid(bytes(v) <= (extra.length ? MAX_RESULT_REQUEST : 4096), 'request byte budget', 400); return v;
}
export function validateLateReply(v, request) {
  valid(exact(v, ['version', 'contract', 'operation', 'account_id', 'native_database_id', 'command_key', 'request_sha256',
    'policy_sha256', 'status', 'replayed', 'code', 'seal_sha256', 'release_stamp'])
    && ['version', 'contract', 'operation', 'account_id', 'native_database_id', 'command_key'].every(k => v[k] === request[k])
    && v.request_sha256 === lateHash(request) && v.policy_sha256 === LATE_POLICY_SHA256 && typeof v.replayed === 'boolean'
    && ['stamped', 'appended', 'already_present', 'rejected'].includes(v.status) && bytes(v) <= 4096, 'reply binding/schema');
  if (v.status === 'rejected') valid(CODES.includes(v.code) && v.replayed === false && v.release_stamp === null && v.seal_sha256 === null, 'rejection envelope');
  else {
    const s = v.release_stamp;
    valid(v.code === null && exact(s, STAMP)
      && ['source_contract', 'run_id', 'battle_id', 'arena_id', 'reservation_id', 'native_inventory_id', 'frozen_sha256'].every(k => s[k] === request[k])
      && typeof s.release_terminal_sha256 === 'string' && SHA.test(s.release_terminal_sha256) && integer(s.finished_revision, 14)
      && ['manual_leave', 'disconnect', 'battle_finished'].includes(s.reason), 'actual release stamp');
    if (v.status === 'stamped') valid(request.operation === 'release_stamp' && !v.replayed && v.seal_sha256 === null, 'read-only stamp status');
    else valid(request.operation === 'append' && typeof v.seal_sha256 === 'string' && SHA.test(v.seal_sha256)
      && s.release_terminal_sha256 === request.release_terminal_sha256 && s.finished_revision === request.finished_revision
      && v.seal_sha256 === createHash('sha256').update(request.seal_json).digest('hex'), 'append exact seal');
  }
  return v;
}
const PENDING = ['version', 'contract', 'operation', 'account_id', 'native_database_id', 'command_key', 'after_arena_id'];
const arena = s => typeof s === 'string' && /^[1-9][0-9]{0,18}$/.test(s) && BigInt(s) <= 9223372036854775807n;
export function validatePendingRequest(v, owner) {
  valid(exact(v, PENDING) && v.version === 1 && v.contract === LATE_CONTRACT && v.operation === 'pending' && v.account_id === owner
    && UUID.test(owner) && integer(v.native_database_id) && typeof v.command_key === 'string' && KEY.test(v.command_key)
    && (v.after_arena_id === null || arena(v.after_arena_id)) && bytes(v) <= 2048, 'pending request binding/schema', 400); return v;
}
export function validatePendingReply(v, request) {
  valid(exact(v, [...PENDING, 'request_sha256', 'policy_sha256', 'status', 'replayed', 'code', 'rows', 'next_arena_id'])
    && PENDING.every(k => v[k] === request[k]) && v.request_sha256 === lateHash(request) && v.policy_sha256 === LATE_POLICY_SHA256
    && v.replayed === false && ['pending', 'rejected'].includes(v.status) && Array.isArray(v.rows) && v.rows.length <= 8 && bytes(v) <= 4096, 'pending reply binding/schema');
  if (v.status === 'rejected') valid(CODES.includes(v.code) && v.rows.length === 0 && v.next_arena_id === null, 'pending rejection');
  else {
    valid(v.code === null, 'pending successful code'); let previous = request.after_arena_id;
    for (const row of v.rows) {
      valid(exact(row, ['arena_id', 'seal_sha256', 'arena_type_id', 'created_unix', 'winner_team', 'own_team', 'vehicle_type_compact_id'])
        && arena(row.arena_id) && (previous === null || previous < row.arena_id) && typeof row.seal_sha256 === 'string' && SHA.test(row.seal_sha256)
        && integer(row.arena_type_id, 1, 65535) && integer(row.created_unix, 0, Number.MAX_SAFE_INTEGER)
        && integer(row.winner_team, 0, 2) && integer(row.own_team, 1, 2) && integer(row.vehicle_type_compact_id, 1, 65535), 'pending actual bounded row/order');
      previous = row.arena_id;
    }
    valid(v.next_arena_id === null || v.rows.length === 8 && v.next_arena_id === v.rows.at(-1).arena_id, 'pending immutable key cursor');
  }
  return v;
}
function file(path, directory = false) {
  valid(typeof path === 'string' && isAbsolute(path) && realpathSync(path).toLowerCase() === resolve(path).toLowerCase()
    && (directory ? statSync(path).isDirectory() : statSync(path).isFile()), 'trusted existing path'); return resolve(path);
}
/** Called only for the authenticated, configured owner; paths never come from JSON. */
export function createLateResultService({ database, originalRoot, accountId, shellCatalog, terminalPolicy, loss, python, worker, cwd, domain = null }) {
  valid(UUID.test(accountId) && typeof loss === 'boolean', 'trusted owner/mode');
  const db = file(database), original = file(originalRoot, true), shells = file(shellCatalog), policy = file(terminalPolicy),
    executable = file(python), script = file(worker), working = file(cwd, true);
  let active = false;
  // DOM-01: the Domain runs tools/p08c_late_results_service for late owners; same bytes and bounds.
  const domainOperation = { append: 'late-append', pending: 'late-pending', battle: 'battle', results: 'results' };
  async function run(operation, request, maximum) {
    valid(!active, 'worker busy', 503); active = true;
    try {
      if (domain !== null) {
        let reply;
        try { reply = await domain.call(domainOperation[operation], accountId, canonicalLate(request), request?.command_key ?? null, LATE_WORKER_TIMEOUT_MS); }
        catch { throw new Error('Late result worker unavailable'); }
        if (reply.status !== 200 || reply.body.length > maximum) throw new Error('Late result worker unavailable');
        try { return JSON.parse(reply.body.toString('utf8')); }
        catch { throw new Error('Late result worker response invalid'); }
      }
      return await new Promise((done, fail) => {
        const env = { ...process.env }; delete env.PYTHONPATH;
        const child = spawn(executable, ['-B', '-X', 'utf8', script, '--database', db, '--original-root', original,
          '--account-id', accountId, '--shell-catalog', shells, '--terminal-policy', policy,
          ...(loss ? ['--ammo-rack-loss'] : []), operation], { cwd: working, env, windowsHide: true, stdio: ['pipe', 'pipe', 'pipe'] });
        let size = 0, errorSize = 0, exceeded = false; const parts = [];
        const timer = setTimeout(() => { exceeded = true; child.kill(); }, LATE_WORKER_TIMEOUT_MS);
        child.stdout.on('data', part => { size += part.length; if (size > maximum) { exceeded = true; child.kill(); } else parts.push(part); });
        child.stderr.on('data', part => { errorSize += part.length; if (errorSize > 4096) { exceeded = true; child.kill(); } });
        child.once('error', () => { clearTimeout(timer); fail(new Error('Late result worker failed')); });
        child.once('close', code => {
          clearTimeout(timer);
          if (code !== 0 || exceeded) return fail(new Error('Late result worker unavailable'));
          try { done(JSON.parse(Buffer.concat(parts).toString('utf8'))); }
          catch { fail(new Error('Late result worker response invalid')); }
        });
        child.stdin.on('error', () => { exceeded = true; child.kill(); }); child.stdin.end(canonicalLate(request));
      });
    } finally { active = false; }
  }
  return {
    async battle(request) {
      const validateRequest = loss ? validateLossBattleRequest : validateMixedBattleRequest;
      const validateReply = loss ? validateLossBattleReply : validateMixedBattleReply;
      validateRequest(request, accountId);
      return validateReply(await run('battle', request, 8192), request);
    },
    async append(request) { validateLateRequest(request, accountId); return validateLateReply(await run('append', request, 4096), request); },
    async pending(request) { validatePendingRequest(request, accountId); return validatePendingReply(await run('pending', request, 4096), request); },
    async results(request) {
      valid(exact(request, ['version', ...(loss ? ['contract'] : []), 'operation', 'account_id', 'native_database_id', 'command_key', 'arena_id'])
        && request.version === (loss ? 4 : 2) && (!loss || request.contract === 'p06t-ammo-rack-loss.v1') && request.account_id === accountId
        && ['query', 'ack'].includes(request.operation) && bytes(request) <= 2048, 'result reader mode/schema', 400);
      // Existing route keeps the unchanged mixed/loss request+reply validators.
      return run('results', request, MAX_RESULT_REQUEST);
    },
  };
}
