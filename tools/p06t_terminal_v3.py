"""Separately pinned seven-profile terminal component. No v1 validator changes."""
from copy import deepcopy
import json
from pathlib import Path

from p06t_owned_registry_v3 import (Registry7, TERMINAL_MANIFEST_SHA256, FROZEN_SCHEMA,
    canonical, sha, require, no_links)
from p06t_terminal import TerminalPolicy

SCHEMA = 'p06t-terminal-policy.v3'
REVISION = 'test_lab.p06t.devices-proxy-fire.v2'
SOURCE_CAPS_SHA256 = '2d74a8e8f272e6305d6779d887cac44ad9794c4ec40807ddf76a5139e3db9da4'
DOCUMENT_SHA256 = '070a819bbe7a42ce7f3fc52f7ce93059c418108ea8d05d8dedd4e9f4d9c6810b'


class TerminalPolicyV3(TerminalPolicy):
    def __init__(self, document, *, registry):
        require(isinstance(registry, Registry7), 'V3_TERMINAL_SOURCE_REQUIRED')
        require(type(document) is dict and set(document) == {'schema', 'policy_revision', 'profiles'}
            and document['schema'] == SCHEMA and document['policy_revision'] == REVISION
            and sha(canonical(document)) == DOCUMENT_SHA256, 'V3_TERMINAL_SOURCE_REQUIRED')
        require(type(document['profiles']) is dict and set(document['profiles']) == set(registry.profiles), 'V3_TERMINAL_SOURCE_REQUIRED')
        for kind, profile in document['profiles'].items():
            source = registry.profiles[kind]
            require(set(profile) == {'max_hp', 'crew_count', 'devices'} and type(profile['max_hp']) is int
                and profile['max_hp'] == source.max_hp and type(profile['crew_count']) is int
                and profile['crew_count'] == len(source.crew_roles) and len(profile['devices']) == 9, 'V3_TERMINAL_SOURCE_REQUIRED')
            for index, row in enumerate(profile['devices']):
                require(type(row) is dict and set(row) == {'extra_index', 'max_health'}
                    and type(row['extra_index']) is int and row['extra_index'] == 26+index
                    and type(row['max_health']) is int and 1 <= row['max_health'] <= 60000, 'V3_TERMINAL_SOURCE_REQUIRED')
        self.registry = registry
        self.document = deepcopy(document)
        self.sha256 = DOCUMENT_SHA256
        self.manifest_sha256 = TERMINAL_MANIFEST_SHA256

    @classmethod
    def from_manifest(cls, path, *, registry):
        path = no_links(Path(path))
        require(path.is_file() and path.stat().st_size == 7652, 'V3_TERMINAL_SOURCE_REQUIRED')
        with path.open('rb') as stream:
            raw = stream.read(32769)
        require(sha(raw) == TERMINAL_MANIFEST_SHA256, 'V3_TERMINAL_SOURCE_REQUIRED')
        value = json.loads(raw)
        require(value['schema'] == 'p06t-device-policy.v2' and value['policy_revision'] == REVISION
            and value['source_caps_sha256'] == SOURCE_CAPS_SHA256 and value['max_primary_seats'] == 6,
            'V3_TERMINAL_SOURCE_REQUIRED')
        document = dict(schema=SCHEMA, policy_revision=REVISION, profiles={p['kind']: dict(max_hp=p['vehicle_max_health'],
            crew_count=len(p['crew']), devices=[{key: row[key] for key in ('extra_index', 'max_health')} for row in p['devices']]) for p in value['profiles']})
        return cls(document, registry=registry)

    def validate(self, raw, *, frozen, terminal_hp, results=None):
        require(type(frozen) is dict and frozen.get('schema') == FROZEN_SCHEMA
            and type(frozen.get('vehicle_inventory_id')) is str, 'V3_FROZEN_REQUIRED')
        account = frozen['vehicle_inventory_id'][:36]
        self.registry.validate_frozen_candidate(frozen, account)
        # Reuse the exact retained field/device/crew/fire/death bounds only
        # after the separate v3 frozen/source/manifest contract has succeeded.
        return TerminalPolicy.validate(self, raw, frozen=frozen, terminal_hp=terminal_hp, results=results)
