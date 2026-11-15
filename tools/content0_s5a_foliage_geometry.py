"""Apply the common foliage size calibration to a verified world-space export."""

import hashlib
import json
import math

from tools.content0_s5a_stand import json_unique


RADIUS_SCALE = 1.05


def encode(document):
    return (json.dumps(document, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False)
            + '\n').encode('ascii')


def scale_basis(basis, factor):
    if (type(basis) is not list or len(basis) != 3
            or any(type(row) is not list or len(row) != 3 for row in basis)):
        raise ValueError('foliage scale requires three world basis rows')
    return [[component * factor for component in row] for row in basis]


def world_aabb_half_extents(basis, shape=None):
    if shape == 'box':
        return [sum(abs(component) for component in axis) for axis in zip(*basis)]
    if shape is not None:
        raise ValueError('unknown foliage volume shape')
    return [math.sqrt(sum(component ** 2 for component in axis)) for axis in zip(*basis)]


def scaled_export(raw, factor=RADIUS_SCALE):
    """Grow shrubs and crowns around their existing centers with one factor.

    The caller pins and validates the input against its map sources. The output
    keeps the source format and carries a derived calibration identity.
    """
    if type(factor) not in (int, float) or not math.isfinite(factor) or factor <= 0:
        raise ValueError('foliage radius scale must be finite and positive')
    if factor == 1:
        return raw
    document = json_unique(raw)
    for row in document['instances']:
        basis = scale_basis(row['basis_world_rows'], factor)
        row['basis_world_rows'] = basis
        row['aabb_half_extents_world'] = world_aabb_half_extents(basis, row.get('shape'))
    for row in document.get('fallen_trees', []):
        row['basis_world_rows'] = scale_basis(row['basis_world_rows'], factor)
    origin = {
        'source_calibration_sha256': document['calibration_sha256'],
        'radius_scale': factor,
        'schema': 'project-foliage-radius-scale.v1',
    }
    document['calibration_sha256'] = hashlib.sha256(encode(origin)).hexdigest()
    return encode(document)
