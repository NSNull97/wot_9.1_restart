# -*- coding: utf-8 -*-
"""Opt-in #717 identity preprocessing. No entity, physics or input mutation.

Queries each ORIGINAL native index, across every destruction family. This
trusted local build artifact is not accepted as live gameplay authority.
Only stdlib imports at module scope: prepare/tests can validate the same schema.
"""
import hashlib
import json
import math
import os
import re
import threading
import time
try:
    import Queue as queue
except ImportError:
    import queue

try:
    integer_types = (int, long)
    string_types = (basestring,)
except NameError:
    integer_types = (int,)
    string_types = (str,)

MAX_SPEC_BYTES = 32768
MAX_OUTPUT_BYTES = 16 * 1024 * 1024
# Whole-map target selection remains bounded and is never truncated. The
# original Prohorovka import selects 44 fragile-containing chunks; two passes
# take 88 observations, within the existing finite load/capture budget.
MAX_CHUNKS_V1 = 64
MAX_CHUNKS_V2 = 128
# Kept as a public compatibility alias for callers that imported the legacy
# bound.  Validation selects the bound from the explicit spec version.
MAX_CHUNKS = MAX_CHUNKS_V1
MAX_ITEMS = 256
MAX_OBSERVATIONS = 300
_probe = None
_done = False
_writer = None
_writer_slot = threading.BoundedSemaphore(1)
WRITER_DEADLINE_SECONDS = 30.0
_now = getattr(time, 'monotonic', None) or time.clock


def require(condition, message):
    if not condition:
        raise ValueError(message)


def freeze_json(value, budget=None, depth=0):
    """Copy plain JSON into immutable tuples; called on one bounded chunk."""
    if budget is None:
        budget = [16384]
    budget[0] -= 1
    require(budget[0] >= 0 and depth <= 12, 'catalog snapshot node/depth bound')
    if type(value) is dict:
        require(all(isinstance(key, string_types) for key in value), 'snapshot keys')
        return ('dict', tuple((key, freeze_json(item, budget, depth + 1))
                              for key, item in value.items()))
    if type(value) is list:
        return ('list', tuple(freeze_json(item, budget, depth + 1) for item in value))
    require(value is None or type(value) in integer_types + (bool, float)
            or isinstance(value, string_types), 'snapshot contains non-JSON object')
    if isinstance(value, string_types):
        require(len(value) <= 1024, 'snapshot string bound')
    if type(value) is float:
        require(not math.isnan(value) and not math.isinf(value), 'snapshot finite number')
    return value


def thaw_json(value):
    """Writer-only conversion; no native objects or callbacks are retained."""
    if type(value) is tuple:
        kind, items = value
        if kind == 'dict':
            return dict((key, thaw_json(item)) for key, item in items)
        require(kind == 'list', 'snapshot tag')
        return [thaw_json(item) for item in items]
    return value


class CatalogWriter(object):
    """One daemon writer, bounded bytes/time, nonblocking main-thread polling.

    A stalled OS write cannot be forcibly interrupted safely. The main thread
    reports its deadline without joining; the daemon retains the pending file
    and refuses publication at its next checkpoint. No second writer starts.
    """
    def __init__(self, snapshot, path, deadline_seconds=WRITER_DEADLINE_SECONDS):
        require(0 < deadline_seconds <= WRITER_DEADLINE_SECONDS, 'writer deadline bound')
        require(_writer_slot.acquire(False), 'catalog writer already running')
        self.path = path
        self.pending = path + '.pending'
        self.failure_path = path + '.failed.json'
        self.started = _now()
        self.deadline = self.started + deadline_seconds
        self.cancelled = threading.Event()
        self.results = queue.Queue(1)
        self.phase = 'queued'
        self.timings = {}
        self.published = False
        self.thread = threading.Thread(target=self._run, args=(snapshot,), name='destructible-catalog-writer')
        self.thread.daemon = True
        try:
            self.thread.start()
        except Exception:
            _writer_slot.release()
            raise

    def _check(self):
        require(not self.cancelled.is_set() and _now() <= self.deadline, 'catalog writer deadline exceeded')

    def _phase(self, name):
        self._check()
        self.phase = name
        self.timings[name] = _now() - self.started

    def _run(self, snapshot):
        result = None
        try:
            self._phase('snapshot_decode')
            value = thaw_json(snapshot)
            self._phase('serialize_write')
            flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, 'O_BINARY', 0)
            require(not os.path.lexists(self.path), 'catalog destination already exists')
            descriptor = os.open(self.pending, flags, 0o600)
            digest = hashlib.sha256()
            size = 0
            with os.fdopen(descriptor, 'wb') as stream:
                encoder = json.JSONEncoder(sort_keys=True, ensure_ascii=True)
                for text in encoder.iterencode(value):
                    self._check()
                    part = text.encode('ascii')
                    size += len(part)
                    require(size + 1 <= MAX_OUTPUT_BYTES, 'catalog output byte bound')
                    stream.write(part)
                    digest.update(part)
                self._check()
                stream.write(b'\n')
                digest.update(b'\n')
                size += 1
                stream.flush()
            self._phase('verify')
            actual = hashlib.sha256()
            total = 0
            with open(self.pending, 'rb') as stream:
                while True:
                    self._check()
                    part = stream.read(65536)
                    if not part:
                        break
                    total += len(part)
                    require(total <= MAX_OUTPUT_BYTES, 'catalog verification byte bound')
                    actual.update(part)
            require(total == size and actual.digest() == digest.digest(), 'catalog output verification failed')
            self._phase('publish')
            # On the supported Windows client os.rename is atomic and refuses
            # an existing target. POSIX link supplies the same no-replace rule
            # for standalone tests; neither path exposes a partial .json.
            if os.name == 'nt':
                os.rename(self.pending, self.path)
            else:
                os.link(self.pending, self.path)
                os.unlink(self.pending)
            self.published = True
            self._phase('complete')
            result = dict(status='complete', path=self.path, sha256=digest.hexdigest(),
                          bytes=size, phase_seconds=dict(self.timings), writer_seconds=_now()-self.started)
        except Exception as error:
            result = dict(status='failed', error=str(error)[:1024], phase=self.phase,
                          path=self.path, pending_path=self.pending, published=self.published,
                          phase_seconds=dict(self.timings), writer_seconds=_now()-self.started)
            try:
                raw = (json.dumps(result, sort_keys=True, ensure_ascii=True) + '\n').encode('ascii')
                require(len(raw) <= 8192, 'writer failure receipt bound')
                descriptor = os.open(self.failure_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, 'O_BINARY', 0), 0o600)
                with os.fdopen(descriptor, 'wb') as stream:
                    stream.write(raw)
                    stream.flush()
                result['failure_receipt'] = self.failure_path
            except Exception as receipt_error:
                result['failure_receipt_error'] = str(receipt_error)[:1024]
        finally:
            _writer_slot.release()
        self.results.put_nowait(result)

    def poll(self):
        try:
            return self.results.get_nowait()
        except queue.Empty:
            if _now() <= self.deadline:
                return None
            self.cancelled.set()
            return dict(status='failed', error='catalog writer deadline exceeded', phase=self.phase,
                        path=self.path, pending_path=self.pending, published=self.published,
                        writer_seconds=_now()-self.started, worker_may_still_be_finishing=True)


def integer(value, minimum, maximum):
    return type(value) in integer_types and minimum <= value <= maximum


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'duplicate catalog spec key')
        result[key] = value
    return result


def validate_spec_payload(payload):
    require(0 < len(payload) <= MAX_SPEC_BYTES, 'catalog spec byte bound')
    # Before JSON recursion/allocation: the schema has only objects/lists and
    # source paths; escaped bracket characters are deliberately disallowed.
    require(payload.count(b'{') <= 18 and payload.count(b'[') <= 2,
            'catalog spec structure bound')
    spec = json.loads(payload.decode('utf-8'), object_pairs_hook=unique_object)
    require(type(spec) is dict and set(spec) == set((
        'version', 'kind', 'map', 'source_pins', 'chunk_ids')), 'catalog spec fields')
    version = spec['version']
    require(type(version) is int and version in (1, 2), 'catalog spec version')
    expected_kind = ('p06o_destructible_catalog_spec' if version == 1
                     else 'p06q_tree_contact_catalog_spec')
    max_chunks = MAX_CHUNKS_V1 if version == 1 else MAX_CHUNKS_V2
    require(spec['kind'] == expected_kind and
            isinstance(spec['map'], string_types) and
            re.match(r'\A[0-9]{2}_[a-z0-9_]{1,48}\Z', spec['map']), 'catalog spec identity')
    chunks = spec['chunk_ids']
    require(type(chunks) is list and 1 <= len(chunks) <= max_chunks and
            all(integer(value, 0, 65535) for value in chunks) and
            chunks == sorted(set(chunks)), 'catalog target chunk bound/order')
    pins = spec['source_pins']
    require(type(pins) is list and 1 <= len(pins) <= 16, 'catalog source pin count')
    paths = set()
    for pin in pins:
        require(type(pin) is dict and set(pin) == set(('path', 'sha256')),
                'catalog source pin fields')
        path, digest = pin['path'], pin['sha256']
        require(isinstance(path, string_types) and 0 < len(path) <= 1024 and
                not any(ord(c) < 32 for c in path) and path not in paths,
                'catalog source pin path')
        require(isinstance(digest, string_types) and
                re.match(r'\A[0-9a-f]{64}\Z', digest), 'catalog source pin digest')
        paths.add(path)
    return spec


def vector(value):
    result = [float(value[i]) for i in range(3)]
    require(all(not math.isnan(x) and not math.isinf(x) and abs(x) <= 32768
                for x in result), 'native catalog vector outside bounds')
    return result


def matrix(value, math_api):
    require(value is not None, 'native catalog matrix missing')
    native = math_api.Matrix(value)
    return dict(axes=[vector(native.applyToAxis(i)) for i in range(3)],
                translation=vector(native.translation))


def resource_name(value):
    require(isinstance(value, string_types) and 0 < len(value) <= 512,
            'native catalog filename missing/outside bound')
    require(not value.startswith(('/', '\\')) and '\\' not in value and
            ':' not in value and all(x not in ('', '.', '..') for x in value.split('/'))
            and not any(ord(x) < 32 for x in value), 'native catalog resource path')
    return value


class Probe(object):
    """One chunk per observation, then a second complete matching observation.

    Missing chunks get a finite load opportunity. Missing native entries,
    changed counts/identities and wrong spaces fail closed, never renumber.
    """
    def __init__(self, spec, spec_sha256):
        self.spec = spec
        self.spec_sha256 = spec_sha256
        self.observations = 0
        self.space = None
        self.previous = None
        self.current = []
        self.waiting = []
        self.complete = False
        self.space_diagnostic = {}
        self.frozen_chunks = []
        self.max_advance_seconds = 0.0

    def advance(self, player, manager, world, math_api):
        require(not self.complete, 'catalog probe already complete')
        self.observations += 1
        native_map = player.arena.arenaType.geometryName
        require(native_map == self.spec['map'],
                'native catalog map differs from spec: actual=%s expected=%r' %
                (repr(native_map)[:80], self.spec['map']))
        space = manager.getSpaceID()
        player_space = player.spaceID
        self.space_diagnostic = dict(manager_space=repr(space)[:80],
                                     player_space=repr(player_space)[:80],
                                     manager_type=type(space).__name__[:80],
                                     player_type=type(player_space).__name__[:80])
        context = ' manager=%r (%s), player=%r (%s)' % (
            space, type(space).__name__, player_space, type(player_space).__name__)
        require(self.observations <= MAX_OBSERVATIONS,
                'catalog load/observation timeout;' + context)
        loaded = manager._DestructiblesManager__loadedChunkIDs
        # Query only automatically selected target keys; no unrelated dictionary
        # or entity enumeration. Retain source index holes as fatal errors.
        counts = [(chunk, loaded.get(chunk)) for chunk in self.spec['chunk_ids']]
        self.waiting = [chunk for chunk, count in counts if count is None]
        # #717 starts the destructibles manager separately from Avatar entry.
        # Like the accepted one-chunk probe, wait for native chunk readiness
        # before binding the initial space. Never query a stale lobby space.
        if self.space is None and self.waiting:
            return None
        require(integer(space, 1, 0x7fffffff) and
                integer(player_space, 1, 0x7fffffff) and space == player_space,
                'native catalog manager/player space mismatch;' + context)
        if self.space is None:
            self.space = space
        require(space == self.space, 'native catalog space changed during capture;' + context)
        if self.waiting:
            if self.current or self.previous is not None:
                raise ValueError('native target chunk unloaded during catalog capture')
            return None
        for chunk, count in counts:
            require(integer(count, 0, MAX_ITEMS), 'native catalog count outside 0..256')
        chunk, count = counts[len(self.current)]
        chunk_matrix = matrix(world.wg_getChunkMatrix(space, chunk), math_api)
        items = []
        for index in range(count):
            filename = resource_name(world.wg_getDestructibleFilename(space, chunk, index))
            local = matrix(world.wg_getDestructibleMatrix(space, chunk, index), math_api)
            items.append(dict(index=index, filename=filename, local_matrix=local))
        require(manager.getSpaceID() == space and loaded.get(chunk) == count,
                'native catalog chunk/space changed during query')
        entry = dict(chunk_id=chunk, count=count, chunk_matrix=chunk_matrix, items=items)
        self.current.append(entry)
        # Freeze only one bounded chunk per callback, during the second pass.
        # Freezing the complete map at handoff would recreate the main-thread
        # stall that this passive observer must avoid.
        if self.previous is not None:
            self.frozen_chunks.append(freeze_json(entry))
        if len(self.current) != len(counts):
            return None
        if self.previous is None:
            self.previous = self.current
            self.current = []
            return None
        require(self.current == self.previous, 'native catalog identity changed between passes')
        self.complete = True
        return dict(version=self.spec['version'],
                    kind=('p06o_destructible_catalog' if self.spec['version'] == 1
                          else 'p06q_tree_contact_catalog'), map=self.spec['map'],
                    space_id=space, source_pins=self.spec['source_pins'],
                    spec_sha256=self.spec_sha256, observation_count=2, chunks=self.current)

    def immutable_snapshot(self, result):
        require(self.complete and result['chunks'] is self.current
                and len(self.frozen_chunks) == len(self.spec['chunk_ids']), 'complete snapshot required')
        metadata = dict((key, value) for key, value in result.items() if key != 'chunks')
        tag, values = freeze_json(metadata)
        return (tag, values + (('chunks', ('list', tuple(self.frozen_chunks))),))


def observe(player, record, settings):
    global _probe, _done, _writer
    if _done:
        return
    try:
        if _writer is not None:
            outcome = _writer.poll()
            if outcome is None:
                return
            _done = True
            if outcome['status'] != 'complete':
                record('destructible_catalog_failed', observer_mutated_gameplay=False,
                       server_hit_authority=False, **outcome)
                return
            record('destructible_catalog', spec_sha256=_probe.spec_sha256,
                   observation_count=2, chunk_count=len(_probe.current),
                   item_count=sum(chunk['count'] for chunk in _probe.current),
                   observer_mutated_gameplay=False, server_hit_authority=False, **outcome)
            return
        import BigWorld
        import Math
        import AreaDestructibles
        from project_preferences import owned
        if _probe is None:
            require(settings.get('enable_shared_lab') is True, 'catalog requires explicit shared lab')
            config = settings.get('destructible_catalog_spec')
            require(type(config) is dict and set(config) == set(('path', 'sha256')),
                    'prepared catalog spec reference missing')
            path = owned(config['path'], settings['local_root'])
            with open(path, 'rb') as stream:
                payload = stream.read(MAX_SPEC_BYTES + 1)
            require(hashlib.sha256(payload).hexdigest() == config['sha256'],
                    'prepared catalog spec hash changed')
            spec = validate_spec_payload(payload)
            _probe = Probe(spec, config['sha256'])
            record('destructible_catalog_started', spec_sha256=config['sha256'],
                   target_chunks=spec['chunk_ids'], observer_mutated_gameplay=False)
        started = _now()
        result = _probe.advance(player, AreaDestructibles.g_destructiblesManager, BigWorld, Math)
        advance_seconds = _now() - started
        _probe.max_advance_seconds = max(_probe.max_advance_seconds, advance_seconds)
        if result is None:
            if _probe.waiting and (_probe.observations == 1 or _probe.observations % 60 == 0):
                record('destructible_catalog_waiting', observation=_probe.observations,
                       waiting_chunks=_probe.waiting, space_state=_probe.space_diagnostic,
                       observer_mutated_gameplay=False, server_hit_authority=False)
            return
        started = _now()
        snapshot = _probe.immutable_snapshot(result)
        directory = owned(settings['trace_dir'], settings['local_root'])
        path = owned(os.path.join(directory, 'destructible-catalog-%d.json' % os.getpid()),
                     settings['local_root'])
        _writer = CatalogWriter(snapshot, path)
        record('destructible_catalog_writer_started', path=path, pending_path=_writer.pending,
               spec_sha256=_probe.spec_sha256, final_advance_seconds=advance_seconds,
               max_advance_seconds=_probe.max_advance_seconds, handoff_seconds=_now()-started,
               writer_deadline_seconds=WRITER_DEADLINE_SECONDS,
               observer_mutated_gameplay=False, server_hit_authority=False)
    except Exception:
        import traceback
        _done = True
        record('destructible_catalog_failed', error=traceback.format_exc(),
               waiting_chunks=_probe.waiting if _probe is not None else [],
               space_state=_probe.space_diagnostic if _probe is not None else {},
               observer_mutated_gameplay=False, server_hit_authority=False)
