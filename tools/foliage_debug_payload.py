"""Join the admitted foliage geometry to the native fallen-tree indices."""

import hashlib

from tools.content0_s5a_foliage_geometry import encode
from tools.content0_s5a_stand import json_unique, read_stable
from tools.prohorovka_foliage import (
    ASSET, BASE_PROHOROVKA_FOLIAGE_SHA256, CATALOG_SHA256, MAX_OUTPUT, PROHOROVKA_FOLIAGE_SHA256,
)


TARGET = 'sr_foliage_debug.json'


def payload(geometry_file, catalog_file):
    raw = read_stable(geometry_file, MAX_OUTPUT)
    source_sha256 = hashlib.sha256(raw).hexdigest()
    if source_sha256 not in (BASE_PROHOROVKA_FOLIAGE_SHA256, PROHOROVKA_FOLIAGE_SHA256):
        raise ValueError('foliage preview requires an admitted geometry artifact')
    catalog_raw = read_stable(catalog_file)
    if hashlib.sha256(catalog_raw).hexdigest() != CATALOG_SHA256:
        raise ValueError('foliage preview requires the admitted Prokhorovka contact catalog')
    document = json_unique(raw)
    catalog = json_unique(catalog_raw)
    if document['map'] != ASSET or catalog['map'] != ASSET or document['fallen_tree_catalog_sha256'] != CATALOG_SHA256:
        raise ValueError('foliage preview map and catalog differ')
    trees = {row['object_id']: row for row in catalog['objects'] if row['kind'] == 'tree'}
    crowns = []
    for crown in document['fallen_trees']:
        tree = trees[crown['object_id']]
        if (tree['instance_id'], tree['resource']) != (crown['instance_id'], crown['resource']):
            raise ValueError('foliage crown differs from its native tree')
        crowns.append({**crown, 'chunk_id': tree['chunk_id'], 'native_index': tree['native_index']})
    encoded = encode({'schema': 'project-foliage-preview.v1', 'map': ASSET, 'source_sha256': source_sha256,
                      'calibration_sha256': document['calibration_sha256'], 'instances': document['instances'],
                      'fallen_trees': crowns})
    if len(encoded) > MAX_OUTPUT:
        raise ValueError('foliage preview exceeds the client payload bound')
    return encoded, {'map': ASSET, 'file': TARGET, 'sha256': hashlib.sha256(encoded).hexdigest()}, {
        'source_sha256': source_sha256, 'catalog_sha256': CATALOG_SHA256,
        'shrubs': len(document['instances']), 'fallen_crowns': len(crowns), 'source_bytes': len(raw),
    }
