# -*- coding: utf-8 -*-
"""Bounded read-only #717 map identity query; never a server hit authority."""
import math

_attempts = 0
_done = False
CHUNK = 31354
RESOURCE = 'mle009_BoxCamouflage'


def vector(value):
    result = [float(value[i]) for i in range(3)]
    if any(math.isnan(v) or math.isinf(v) or abs(v) > 4096 for v in result):
        raise ValueError('destructible vector outside bounds')
    return result


def matrix(value, Math):
    m = Math.Matrix(value)
    return dict(translation=vector(m.translation),
                axes=[vector(m.applyToAxis(i)) for i in range(3)])


def observe(player, record):
    global _attempts, _done
    if _done:
        return
    _attempts += 1
    try:
        import BigWorld
        import Math
        import AreaDestructibles
        manager = AreaDestructibles.g_destructiblesManager
        if not manager.isChunkLoaded(CHUNK):
            if _attempts >= 60:
                _done = True
                record('destructible_identity_unavailable', reason='chunk not loaded in 60 observations',
                       chunk_id=CHUNK, observer_mutated_gameplay=False)
            return
        _done = True
        space = manager.getSpaceID()
        if space != player.spaceID:
            raise ValueError('destructible manager space differs from player')
        count = manager._DestructiblesManager__loadedChunkIDs.get(CHUNK)
        if type(count) not in (int, long) or not 0 <= count <= 256:
            raise ValueError('native destructible count outside bounds')
        chunk_matrix = matrix(BigWorld.wg_getChunkMatrix(space, CHUNK), Math)
        filenames = []
        matches = []
        for index in range(count):
            filename = BigWorld.wg_getDestructibleFilename(space, CHUNK, index)
            if not isinstance(filename, basestring) or len(filename) > 512:
                raise ValueError('native destructible filename outside bounds')
            filenames.append(dict(index=index, filename=filename))
            if RESOURCE in filename:
                local = matrix(BigWorld.wg_getDestructibleMatrix(space, CHUNK, index), Math)
                matches.append(dict(index=index, filename=filename, local_matrix=local,
                    world_translation=[a + b for a, b in zip(chunk_matrix['translation'], local['translation'])]))
        predicates = []
        def accept(material, flags, item, chunk):
            if len(predicates) >= 256:
                raise ValueError('native ray predicate bound exceeded')
            values = (material, flags, item, chunk)
            if any(type(v) not in (int, long) or not 0 <= v <= 0xffffffff for v in values):
                raise ValueError('native ray identity shape differs')
            predicates.append(dict(material_kind=material, flags=flags, item_id=item, chunk_id=chunk))
            return True
        rays = []
        for y in (56.2, 57.0, 57.7):
            for axis in (0, 2):
                start = [-402.3, y, -404.5]
                end = list(start)
                start[axis] -= 10.
                end[axis] += 10.
                hit = BigWorld.wg_collideSegment(space, Math.Vector3(*start), Math.Vector3(*end), 128, accept)
                row = dict(start=start, end=end, hit=None)
                if hit is not None:
                    if len(hit) != 6:
                        raise ValueError('native segment hit shape differs')
                    row['hit'] = dict(point=vector(hit[0]), material_kind=hit[2], item_id=hit[4], chunk_id=hit[5])
                rays.append(row)
        record('destructible_identity', version=1, space_id=space, chunk_id=CHUNK,
               count=count, chunk_matrix=chunk_matrix, filenames=filenames,
               matches=matches, rays=rays, predicates=predicates,
               observer_mutated_gameplay=False, server_hit_authority=False)
    except Exception:
        _done = True
        import traceback
        record('destructible_identity_failed', error=traceback.format_exc(),
               observer_mutated_gameplay=False)
