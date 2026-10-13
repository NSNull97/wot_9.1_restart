"""Configuration/path boundaries only; synthetic files are not native evidence."""
import hashlib
import json
from pathlib import Path
import stat
import tempfile
import types
import unittest
from unittest.mock import patch

from tools import destructible_catalog as config
from tools import p03i_static_audit as queue
from tools import p07a_visibility_static_audit as visibility


class ClientSourcePathsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.repository = self.base / 'repository'
        self.original = self.base / 'external-original'
        self.research = self.repository / 'research'
        self.local = self.repository / 'local'
        for directory in (self.original, self.research, self.local, self.repository / 'config'):
            directory.mkdir(parents=True, exist_ok=True)
        self.config_path = self.repository / 'config/project.local.json'
        self.paths = {'original_client_root': str(self.original),
                      'research_client_root': str(self.research),
                      'local_artifacts_root': str(self.local)}
        self.write_config()

    def write_config(self):
        self.config_path.write_text(json.dumps({'paths': self.paths}), encoding='utf-8-sig')

    def test_explicit_repository_config_resolves_relocated_original(self):
        with patch.object(config, 'ROOT', self.base / 'unused-default'):
            paths = config.configured_paths(self.repository)
        self.assertEqual(self.original, paths['original_client_root'])
        self.assertEqual(self.research, paths['research_client_root'])
        self.assertEqual(self.local, paths['local_artifacts_root'])

    def test_default_repository_and_matching_overrides_remain_supported(self):
        with patch.object(config, 'ROOT', self.repository):
            paths = config.configured_paths(original=self.original, research='research')
        self.assertEqual(self.original, paths['original_client_root'])

    def test_arbitrary_override_and_cross_copy_override_rejected(self):
        for directory in (self.local, self.research, self.base):
            with self.subTest(directory=directory), self.assertRaises(config.CatalogError):
                config.configured_paths(self.repository, original=directory)

    def test_parent_traversal_even_to_configured_copy_rejected(self):
        with self.assertRaises(config.CatalogError):
            config.configured_paths(self.repository, original='../external-original')

    def test_relative_configured_source_rejected(self):
        self.paths['original_client_root'] = '../external-original'
        self.write_config()
        with self.assertRaises(config.CatalogError):
            config.configured_paths(self.repository)

    def test_output_root_must_remain_repository_local(self):
        self.paths['local_artifacts_root'] = str(self.base)
        self.write_config()
        with self.assertRaises(config.CatalogError):
            config.configured_paths(self.repository)

    def test_client_cannot_be_output_or_same_copy(self):
        for directory in (self.local, self.research):
            self.paths['original_client_root'] = str(directory)
            self.write_config()
            with self.subTest(directory=directory), self.assertRaises(config.CatalogError):
                config.configured_paths(self.repository)

    def test_configured_source_must_be_existing_directory(self):
        self.paths['original_client_root'] = str(self.config_path)
        self.write_config()
        with self.assertRaises(config.CatalogError):
            config.configured_paths(self.repository)
        self.paths['original_client_root'] = str(self.base / 'missing')
        self.write_config()
        with self.assertRaises(FileNotFoundError):
            config.configured_paths(self.repository)

    def test_config_size_and_duplicate_keys_rejected(self):
        for raw in (' ' * 65537, '{"paths":{},"paths":{}}'):
            self.config_path.write_text(raw, encoding='utf-8')
            with self.subTest(raw_length=len(raw)), self.assertRaises(config.CatalogError):
                config.configured_paths(self.repository)

    def test_linked_source_config_and_nested_resource_rejected(self):
        resource = self.original / 'source.pyc'
        resource.write_bytes(b'synthetic')
        for link, mode in ((self.original, stat.S_IFLNK), (self.config_path, stat.S_IFLNK),
                           (resource, stat.S_IFLNK), (self.original, stat.S_IFDIR),
                           (resource, stat.S_IFREG)):
            # Deterministic filesystem metadata injection also works without
            # Windows symlink privileges; no real link is created or followed.
            actual_lstat = Path.lstat
            def lstat(path, *args, **kwargs):
                if path == link:
                    return types.SimpleNamespace(st_mode=mode,
                                                 st_file_attributes=getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 1024))
                return actual_lstat(path, *args, **kwargs)
            with self.subTest(link=link, mode=mode), patch.object(Path, 'lstat', lstat):
                if link == resource:
                    for module, error in ((queue, queue.P03IStaticAuditError),
                                          (visibility, visibility.P07AVisibilityAuditError)):
                        with self.assertRaises(error):
                            module._read(self.original, resource)
                else:
                    with self.assertRaises(config.CatalogError):
                        config.configured_paths(self.repository)

    def test_source_hashing_uses_its_bound_and_evidence_cannot_escape_repository(self):
        raw = b'synthetic-source-only'
        resource = self.original / 'source.pyc'
        resource.write_bytes(raw)
        digest = hashlib.sha256(raw).hexdigest()
        self.assertEqual(digest, queue._hash(self.repository, self.original, 'source.pyc', digest))
        row = visibility._hash_copy(self.repository, self.original, 'source.pyc', (len(raw), digest))
        self.assertEqual(digest, row['sha256'])
        for module, error in ((queue, queue.P03IStaticAuditError),
                              (visibility, visibility.P07AVisibilityAuditError)):
            with self.subTest(module=module.__name__):
                with self.assertRaises(error):
                    module._read(self.repository, resource)
                with self.assertRaises(error):
                    module._read(self.original, '../repository/config/project.local.json')
                with self.assertRaises(error):
                    module._bounded(self.repository, self.original / 'receipt.json', must_exist=False)


if __name__ == '__main__':
    unittest.main()
