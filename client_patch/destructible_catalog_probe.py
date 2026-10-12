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
MAX_CHUNKS = 64
MAX_ITEMS = 256
MAX_OBSERVATIONS = 300
_probe = None
_done = False


def require(condition, message):
    if not condition:
        raise ValueError(message)


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
    require(type(spec['version']) is int and spec['version'] == 1 and
            spec['kind'] == 'p06o_destructible_catalog_spec' and
            isinstance(spec['map'], string_types) and
            re.match(r'\A[0-9]{2}_[a-z0-9_]{1,48}\Z', spec['map']), 'catalog spec identity')
    chunks = spec['chunk_ids']
    require(type(chunks) is list and 1 <= len(chunks) <= MAX_CHUNKS and
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
        self.current.append(dict(chunk_id=chunk, count=count,
                                 chunk_matrix=chunk_matrix, items=items))
        if len(self.current) != len(counts):
            return None
        if self.previous is None:
            self.previous = self.current
            self.current = []
            return None
        require(self.current == self.previous, 'native catalog identity changed between passes')
        self.complete = True
        return dict(version=1, kind='p06o_destructible_catalog', map=self.spec['map'],
                    space_id=space, source_pins=self.spec['source_pins'],
                    spec_sha256=self.spec_sha256, observation_count=2, chunks=self.current)


def observe(player, record, settings):
    global _probe, _done
    if _done:
        return
    try:
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
        result = _probe.advance(player, AreaDestructibles.g_destructiblesManager, BigWorld, Math)
        if result is None:
            if _probe.waiting and (_probe.observations == 1 or _probe.observations % 60 == 0):
                record('destructible_catalog_waiting', observation=_probe.observations,
                       waiting_chunks=_probe.waiting, space_state=_probe.space_diagnostic,
                       observer_mutated_gameplay=False, server_hit_authority=False)
            return
        payload = (json.dumps(result, sort_keys=True, ensure_ascii=True) + '\n').encode('ascii')
        require(len(payload) <= MAX_OUTPUT_BYTES, 'catalog output byte bound')
        directory = owned(settings['trace_dir'], settings['local_root'])
        path = owned(os.path.join(directory, 'destructible-catalog-%d.json' % os.getpid()),
                     settings['local_root'])
        flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, 'O_BINARY', 0)
        descriptor = os.open(path, flags, 0o600)
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(payload)
            stream.flush()
        digest = hashlib.sha256(payload).hexdigest()
        with open(path, 'rb') as stream:
            require(hashlib.sha256(stream.read(MAX_OUTPUT_BYTES + 1)).hexdigest() == digest,
                    'catalog output verification failed')
        _done = True
        record('destructible_catalog', status='complete', path=path, sha256=digest,
               spec_sha256=_probe.spec_sha256, observation_count=2,
               chunk_count=len(result['chunks']), item_count=sum(c['count'] for c in result['chunks']),
               observer_mutated_gameplay=False, server_hit_authority=False)
    except Exception:
        import traceback
        _done = True
        record('destructible_catalog_failed', error=traceback.format_exc(),
               waiting_chunks=_probe.waiting if _probe is not None else [],
               space_state=_probe.space_diagnostic if _probe is not None else {},
               observer_mutated_gameplay=False, server_hit_authority=False)
