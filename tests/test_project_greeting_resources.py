"""Bounded parser controls plus read-only exact original #717 resource checks.

Synthetic malformed catalogs are unit inputs, never native compatibility proof.
No generated resource is written to client copies or the tracked repository.
"""
import gettext
import hashlib
import io
import json
from pathlib import Path
import struct
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import project_greeting_resources as greeting


def synthetic_catalog():
    return greeting._encode(((b'', b'Content-Type: text/plain; charset=UTF-8\n'),
                             (b'connected', b'Own unit server %s'), (b'other', b'Unchanged')))


def field(raw, offset, value):
    changed = bytearray(raw)
    struct.pack_into('<I', changed, offset, value)
    return bytes(changed)


class BoundedMOControls(unittest.TestCase):
    def test_wrong_type_or_byte_bound(self):
        for raw in ('text', bytearray(28), b'', bytes(27), bytes(greeting.MAX_MO_BYTES + 1)):
            with self.subTest(kind=type(raw).__name__, size=len(raw)):
                with self.assertRaises(ValueError):
                    greeting.project_greeting(raw)

    def test_synthetic_is_never_accepted_as_original(self):
        with self.assertRaisesRegex(ValueError, 'source SHA/size'):
            greeting.project_greeting(synthetic_catalog())

    def test_magic_revision_count_bounds(self):
        raw = synthetic_catalog()
        for offset, value in ((0, 0), (0, 0xDE120495), (4, 1), (8, 0), (8, 1025), (8, 0xFFFFFFFF)):
            with self.subTest(offset=offset, value=value):
                with self.assertRaises(ValueError):
                    greeting._catalog(field(raw, offset, value))

    def test_descriptor_table_bounds_alignment_overlap(self):
        raw = synthetic_catalog()
        for offset, value in ((12, 0), (12, 29), (12, 0xFFFFFFFC), (16, 28), (16, len(raw) - 4)):
            with self.subTest(offset=offset, value=value):
                with self.assertRaises(ValueError):
                    greeting._catalog(field(raw, offset, value))

    def test_hash_table_bounds_and_overlap(self):
        raw = synthetic_catalog()
        for candidate in (field(raw, 20, 2049), field(raw, 24, 28),
                          field(field(raw, 20, 3), 24, 28), field(field(raw, 20, 3), 24, 0xFFFFFFFC)):
            with self.assertRaises(ValueError):
                greeting._catalog(candidate)

    def test_invalid_hash_entry(self):
        raw = synthetic_catalog()
        strings_at = 28 + 3 * 16
        changed = bytearray(raw[:strings_at] + struct.pack('<I', 4) + raw[strings_at:])
        struct.pack_into('<2I', changed, 20, 1, strings_at)
        for i in range(6):
            offset = 28 + i * 8 + 4
            struct.pack_into('<I', changed, offset, struct.unpack_from('<I', changed, offset)[0] + 4)
        with self.assertRaisesRegex(ValueError, 'hash entry'):
            greeting._catalog(bytes(changed))

    def test_string_length_offset_terminator(self):
        raw = synthetic_catalog()
        for candidate in (field(raw, 36, greeting.MAX_STRING_BYTES + 1),
                          field(raw, 40, 0), field(raw, 40, 0xFFFFFFFF), raw[:-1]):
            with self.assertRaises(ValueError):
                greeting._catalog(candidate)
        changed = bytearray(raw)
        length, offset = struct.unpack_from('<2I', changed, 36)
        changed[offset + length] = 65
        with self.assertRaisesRegex(ValueError, 'terminator'):
            greeting._catalog(bytes(changed))

    def test_duplicate_or_unsorted_keys(self):
        raw = bytearray(synthetic_catalog())
        raw[44:52] = raw[36:44]
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            greeting._catalog(bytes(raw))
        for pairs in (((b'', b''), (b'z', b'z'), (b'a', b'a')),
                      ((b'', b''), (b'a', b'1'), (b'a', b'2'))):
            with self.assertRaises(ValueError):
                greeting._encode(pairs)

    def test_missing_metadata(self):
        with self.assertRaisesRegex(ValueError, 'keys'):
            greeting._encode(((b'connected', b'%s'),))

    def test_embedded_nul_and_invalid_utf8(self):
        raw = synthetic_catalog()
        length, offset = struct.unpack_from('<2I', raw, 36)
        for replacement in (0, 255):
            changed = bytearray(raw)
            changed[offset] = replacement
            with self.assertRaises(ValueError):
                greeting._catalog(bytes(changed))
        with self.assertRaises(ValueError):
            greeting._encode(((b'', b''), (b'connected', b'plural\0%s')))

    def test_absent_duplicate_connected_key(self):
        for pairs in (((b'', b''),), ((b'connected', b'%s'), (b'connected', b'%s'))):
            with self.assertRaisesRegex(ValueError, 'connected key'):
                greeting._replace_connected(pairs)

    def test_exact_single_placeholder(self):
        for value in (b'none', b'%s %s', b'%d', b'%(server)s', b'%%s', b'%s %%', b'%s %q'):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    greeting._replace_connected(((b'', b''), (b'connected', value)))
        result = greeting._replace_connected(((b'', b''), (b'connected', b'Welcome %s')))
        self.assertEqual(result[1], (b'connected', greeting.GREETING.encode('utf8')))

    def test_writer_rejects_unbounded_entries_and_strings(self):
        for pairs in ([], [None], [(b'', bytearray())], [(b'', b'x' * 4097)], [(b'', b'')] * 1025):
            with self.assertRaises(ValueError):
                greeting._encode(pairs)


class OriginalCatalogReadOnly(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = ROOT / 'config/project.local.json'
        if not path.exists():
            raise unittest.SkipTest('Exact local client configuration absent; native resource check NOT_RUN')
        config = json.loads(path.read_bytes())
        cls.source = Path(config['paths']['original_client_root']) / greeting.SOURCE
        if not cls.source.exists():
            raise unittest.SkipTest('Original resource absent; no client data is fabricated')
        cls.raw = cls.source.read_bytes()

    def test_actual_original_exact_hash_and_all_catalog_values(self):
        before_hash = hashlib.sha256(self.raw).hexdigest()
        payload, evidence = greeting.project_greeting(self.raw)
        original = gettext.GNUTranslations(io.BytesIO(self.raw))
        changed = gettext.GNUTranslations(io.BytesIO(payload))
        before = original._catalog
        after = changed._catalog
        self.assertEqual(before_hash, greeting.SOURCE_SHA256)
        self.assertEqual(set(before), set(after))
        self.assertEqual(len(before), 656)
        self.assertEqual([key for key in before if before[key] != after[key]], ['connected'])
        self.assertEqual(after['connected'], greeting.GREETING)
        self.assertEqual(after['connected'] % 'Стальной рубеж', 'Добро пожаловать на сервер «Стальной рубеж»!')
        self.assertEqual(before[''], after[''])
        self.assertEqual(evidence['unchanged_values'], 655)
        self.assertEqual(evidence['native_render'], 'NOT_RUN')
        self.assertEqual(hashlib.sha256(self.source.read_bytes()).hexdigest(), before_hash)

    def test_actual_resource_changed_byte_rejected(self):
        raw = bytearray(self.raw)
        raw[-2] ^= 1
        with self.assertRaisesRegex(ValueError, 'source SHA/size'):
            greeting.project_greeting(bytes(raw))

    def test_actual_output_is_deterministic_and_cannot_be_repatched(self):
        first, evidence1 = greeting.project_greeting(self.raw)
        second, evidence2 = greeting.project_greeting(self.raw)
        self.assertEqual(first, second)
        self.assertEqual(evidence1, evidence2)
        self.assertEqual(evidence1['output_sha256'], hashlib.sha256(first).hexdigest())
        with self.assertRaisesRegex(ValueError, 'source SHA/size'):
            greeting.project_greeting(first)


if __name__ == '__main__':
    unittest.main(verbosity=2)
