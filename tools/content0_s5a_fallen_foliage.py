"""Derive local crown volumes from the checked Malinovka contact catalogue."""

import hashlib
import math
from pathlib import Path

from tools.content0_s5a_stand import ROOT, json_unique, no_link, read_stable
from tools.malinovka_bush_volumes import determinant


CALIBRATION = ROOT / 'config/rulesets/content0-s5a-fallen-tree-crowns.v1.json'
PHYSICS_MANIFEST = Path('resources/evidence/20261020-maps01/final01/packages/02_malinovka/physics/manifest.json')
CATALOG_SHA256 = '61dd9a2300dd3dc965656a81126b43cd20debaa91ed35808e247619c0276723f'
TREE_COUNT = 989
CALIBRATION_SCHEMA = 'content0-s5a-fallen-tree-crowns.v1'


def pinned_json(path, boundary, expected):
    no_link(path, boundary)
    raw = read_stable(path)
    if hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError('fallen foliage source SHA-256 mismatch')
    return json_unique(raw)


def numeric_vector(values, count, lower, upper):
    return (type(values) is list and len(values) == count
            and all(type(v) in (int, float) and math.isfinite(v) and lower <= v <= upper for v in values))


def build_rows(catalog, physics, calibration):
    if (catalog['map'] != '02_malinovka' or catalog['version'] != 8 or catalog['contacts'] is not True
        or physics['map'] != '02_malinovka' or calibration['schema'] != CALIBRATION_SCHEMA
        or calibration['map'] != '02_malinovka' or calibration['classification'] != 'PROJECT_CALIBRATION_NOT_HISTORICAL'):
        raise ValueError('fallen foliage source identity mismatch')
    trees = [item for item in catalog['objects'] if item['kind'] == 'tree']
    settings = calibration['resources']
    if len(trees) != TREE_COUNT or set(settings) != {tree['resource'] for tree in trees}:
        raise ValueError('fallen foliage requires the complete approved tree catalogue')
    for resource, row in settings.items():
        if (not resource.startswith('speedtree/02_Malinovka/') or not resource.endswith('.spt')
            or set(row) != {'sha256','bytes','canopy_class','center_local','radii_local','concealment_additive'}
            or type(row['sha256']) is not str or len(row['sha256']) != 64 or any(c not in '0123456789abcdef' for c in row['sha256'])
            or type(row['bytes']) is not int or not 0 < row['bytes'] <= 8 * 1024 * 1024
            or row['canopy_class'] not in ('leafy','needle','sparse_unknown','bare')
            or not numeric_vector(row['center_local'], 3, -100, 100)
            or not numeric_vector(row['radii_local'], 3, 0.01, 100)
            or not numeric_vector([row['concealment_additive']], 1, 0, 1)
            or (row['concealment_additive'] == 0) != (row['canopy_class'] == 'bare')):
            raise ValueError('fallen foliage crown calibration mismatch')

    result = []
    seen = set()
    last_object_id = 0
    instances = physics['instances']
    for tree in trees:
        object_id = tree['object_id']
        instance_id = tree['instance_id']
        if (type(object_id) is not int or not last_object_id < object_id <= 0xffffffff
            or type(instance_id) is not int or not 0 <= instance_id < len(instances) or instance_id in seen):
            raise ValueError('fallen foliage tree index and identity mismatch')
        last_object_id = object_id
        seen.add(instance_id)
        source = instances[instance_id]
        resource = tree['resource']
        chunk = source['chunk']
        if (source['kind'] != 'speedtree' or source['resource'] != resource
            or source['first_triangle'] != tree['physics_first_triangle'] or source['triangles'] != tree['physics_triangle_count']
            or not numeric_vector(chunk, 2, -6, 5) or any(type(value) is not int for value in chunk)
            or tree['chunk_id'] != ((chunk[0] + 127) << 8) | (chunk[1] + 127)):
            raise ValueError('fallen foliage tree does not match physics manifest instance')
        transform = source['transform']
        if not numeric_vector(transform, 12, -10000, 10000):
            raise ValueError('fallen foliage transform bounds')
        setting = settings[resource]
        root = [transform[9] + 100 * chunk[0], transform[10], transform[11] + 100 * chunk[1]]
        offset = [sum(setting['center_local'][row] * transform[3*row+axis] for row in range(3)) for axis in range(3)]
        basis = [[setting['radii_local'][row] * transform[3*row+axis] for axis in range(3)] for row in range(3)]
        if (not numeric_vector(root, 3, -10000, 10000) or not numeric_vector(offset, 3, -1000, 1000)
            or any(not numeric_vector(row, 3, -1000, 1000) for row in basis) or abs(determinant(basis)) < 1e-8):
            raise ValueError('fallen foliage world crown bounds')
        result.append({'object_id':object_id,'instance_id':instance_id,'resource':resource,'root_world':root,
                       'center_from_root_world':offset,'basis_world_rows':basis,'concealment_additive':setting['concealment_additive']})
    return result


def load_fallen_sources(stand, scene, profiles):
    """Bind crown data to the same pinned catalogue the battle worker uses."""
    catalog_ref = profiles['catalog']
    if profiles['map'] != '02_malinovka' or catalog_ref['sha256'] != CATALOG_SHA256:
        raise ValueError('unapproved fallen foliage battle catalogue')
    catalog_path = Path(catalog_ref['path'])
    if not catalog_path.is_absolute():
        raise ValueError('fallen foliage catalogue requires an absolute local path')
    catalog = pinned_json(catalog_path, stand, CATALOG_SHA256)
    pins = scene['source_pins']
    if (catalog['physics_manifest_sha256'] != pins['physics_manifest_sha256']
        or catalog['projectile_manifest_sha256'] != pins['projectile_manifest_sha256']):
        raise ValueError('fallen foliage contact catalogue and map pin mismatch')
    physics = pinned_json(stand / PHYSICS_MANIFEST, stand, pins['physics_manifest_sha256'])
    no_link(CALIBRATION, ROOT)
    raw_calibration = read_stable(CALIBRATION, limit=32*1024)
    crowns = build_rows(catalog, physics, json_unique(raw_calibration))
    return {'fallen_tree_catalog_sha256':CATALOG_SHA256,'fallen_trees':crowns}, hashlib.sha256(raw_calibration).hexdigest()
