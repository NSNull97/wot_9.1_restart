"""Derived catalogue cache and digest memo keep results identical and fail closed.

Original-source tests skip explicitly (NOT_RUN) without the owner-authorized
original; they only read it. Cache files live in a private temporary directory.
"""
import hashlib
import json
import marshal
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from tools import p09e_research_catalog as catalog
from tools.destructible_catalog import CatalogError, no_links


def fresh_sha(document):
    return hashlib.sha256(catalog.canonical(document)).hexdigest()


def exact(document):
    """Version 2 marshal: values, types and insertion order, no refcount-dependent refs."""
    return marshal.dumps(document, 2)


class DigestMemoTests(unittest.TestCase):
    def test_every_mutation_recomputes_the_canonical_digest(self):
        document = {"b": [1, {"x": "y"}], "a": 1}
        value = catalog.Catalog(document)
        self.assertEqual(fresh_sha(document), value.sha256)
        self.assertEqual(fresh_sha(document), value.sha256)  # memo hit
        for mutate in (lambda d: d["b"][1].update(x="z"), lambda d: d["b"].append(2),
                       lambda d: d.update(a=True), lambda d: d.update(a=1.0), lambda d: d.update(a=1),
                       lambda d: d.pop("b"), lambda d: d.update(c=None)):
            mutate(document)
            self.assertEqual(fresh_sha(document), value.sha256)

    def test_unmarshallable_document_keeps_canonical_failure(self):
        value = catalog.Catalog({"a": object()})
        with self.assertRaises(TypeError): value.sha256


@unittest.skipUnless(os.name == "nt", "NOT_RUN: Windows junction semantics")
class LinkCheckTests(unittest.TestCase):
    def test_junction_and_missing_components_keep_their_results(self):
        with tempfile.TemporaryDirectory() as tmp:
            target, junction = Path(tmp) / "target", Path(tmp) / "junction"
            target.mkdir()
            subprocess.run(["cmd", "/c", "mklink", "/J", str(junction), str(target)],
                           check=True, capture_output=True)
            try:
                with self.assertRaisesRegex(CatalogError, "reparse path forbidden"):
                    no_links(junction / "file.json")
                self.assertEqual(Path(tmp, "absent", "x").absolute(), no_links(Path(tmp, "absent", "x")))
                with self.assertRaisesRegex(CatalogError, "parent traversal"):
                    no_links(Path(tmp) / ".." / "x")
            finally:
                subprocess.run(["cmd", "/c", "rmdir", str(junction)], check=True, capture_output=True)


class OriginalCacheTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original = Path(os.environ.get("WOT_P09E_ORIGINAL", r"C:\WoT_0.9.1_RU_0717_original"))
        if not cls.original.is_dir():
            raise unittest.SkipTest("NOT_RUN: pinned original #717 source root unavailable")
        cls.reference = catalog.load_catalog(cls.original, cache_dir=None)
        cls.exact = exact(cls.reference.document)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.cache = Path(self.tmp.name) / "cache"

    def load(self):
        return catalog.load_catalog(self.original, cache_dir=self.cache)

    def cache_file(self):
        files = list(self.cache.glob("*.json"))
        self.assertEqual(1, len(files))
        return files[0]

    def test_cold_and_warm_loads_are_byte_identical_to_the_uncached_build(self):
        cold = self.load()
        path = self.cache_file()
        warm = self.load()
        for value in (cold, warm):
            self.assertEqual(self.exact, exact(value.document))
            self.assertEqual(self.reference.sha256, value.sha256)
            self.assertEqual(catalog.canonical(self.reference.audit), catalog.canonical(value.audit))
        self.assertEqual([path], list(self.cache.glob("*.json")))
        self.assertEqual([], list(self.cache.glob(".tmp-*")))

    def test_corrupt_or_mismatching_cache_files_are_rebuilt_never_used(self):
        self.load()
        path = self.cache_file()
        original = path.read_bytes()
        header, _, body = original.partition(b"\n")
        meta = json.loads(header)
        tampered_body = body.replace(b'"tier":1,', b'"tier":2,', 1)
        self.assertNotEqual(body, tampered_body)
        relabelled = dict(meta, document_sha256=hashlib.sha256(tampered_body).hexdigest())
        variants = {
            "truncated": original[:len(original) // 2],
            "body-flip": header + b"\n" + tampered_body,
            "stale-catalog-digest": catalog.canonical(relabelled) + b"\n" + tampered_body,
            "foreign-key": catalog.canonical(dict(meta, key="0" * 64)) + b"\n" + body,
            "wrong-schema": catalog.canonical(dict(meta, cache="other")) + b"\n" + body,
            "not-json": b"\x00" * 64,
        }
        for name, raw in variants.items():
            with self.subTest(name):
                path.write_bytes(raw)
                value = self.load()
                self.assertEqual(self.exact, exact(value.document))
                self.assertEqual(original, path.read_bytes())  # rebuilt and rewritten

    def test_cached_document_still_requires_every_pinned_source(self):
        self.load()
        path = self.cache_file()
        pins = json.loads(catalog.PIN_PATH.read_text())["sources"]
        with tempfile.TemporaryDirectory() as empty:
            with self.assertRaises(CatalogError):
                catalog._cached_catalog(path, Path(empty).resolve(), pins)
        with tempfile.TemporaryDirectory() as tmp:
            changed = json.loads(catalog.PIN_PATH.read_text())
            changed["sources"]["res/scripts/common/items/vehicles.pyc"]["sha256"] = "0" * 64
            manifest = Path(tmp) / "pins.json"
            manifest.write_text(json.dumps(changed))
            with self.assertRaises(catalog.ResearchCatalogError):
                catalog.load_catalog(self.original, manifest, cache_dir=self.cache)
            # A cache entry for the real manifest never answers for another manifest.
            self.assertIsNone(catalog._cached_catalog(path, self.original.resolve(), changed["sources"]))

    def test_code_or_manifest_change_selects_a_new_cache_key(self):
        root = self.original.resolve()
        manifest = catalog.PIN_PATH.read_bytes()
        base = catalog._cache_path(self.cache, root, manifest)
        self.assertNotEqual(base, catalog._cache_path(self.cache, root, manifest + b" "))
        self.assertNotEqual(base, catalog._cache_path(self.cache, Path(self.tmp.name), manifest))
        self.assertIsNone(catalog._cache_path(None, root, manifest))

    @unittest.skipUnless(os.name == "nt", "NOT_RUN: Windows junction semantics")
    def test_linked_cache_location_is_neither_read_nor_written(self):
        target = Path(self.tmp.name) / "target"
        target.mkdir()
        subprocess.run(["cmd", "/c", "mklink", "/J", str(self.cache), str(target)],
                       check=True, capture_output=True)
        try:
            value = self.load()
            self.assertEqual(self.exact, exact(value.document))
            self.assertEqual([], list(target.iterdir()))
        finally:
            subprocess.run(["cmd", "/c", "rmdir", str(self.cache)], check=True, capture_output=True)


if __name__ == "__main__": unittest.main()
