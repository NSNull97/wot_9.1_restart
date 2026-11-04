"""Synthetic binary boundary tests; not native game validation."""
import hashlib
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

from tools import packed_xml
from tools import shell_mech_source_audit as audit


def sample():
    # Two repeated fields, one nested armor element, one zero-width bool.
    names = b"count\0armor\0screen\0\0"
    nested = struct.pack("<HI", 1, 0x10000000)
    nested += struct.pack("<HI", 2, 0x40000000)
    root = struct.pack("<HI", 3, 0x10000000)
    root += struct.pack("<HI", 0, 0x20000001)
    root += struct.pack("<HI", 0, 0x20000002)
    root += struct.pack("<HI", 1, 2 + len(nested))
    return packed_xml.MAGIC + b"\0" + names + root + b"\x06\x04" + nested


class SourceAuditTests(unittest.TestCase):
    def test_raw_offsets_repeated_names_nested_and_empty(self):
        data = sample()
        rows = {row["path"]: row for row in audit.field_offsets(data)}
        self.assertEqual(set(rows), {"/", "/count[1]", "/count[2]",
                                     "/armor[1]", "/armor[1]/screen[1]"})
        for path, number in (("/count[1]", 6), ("/count[2]", 4)):
            row = rows[path]
            self.assertEqual(row["value"], number)
            self.assertEqual(data[row["value_start"]:row["value_end"]], bytes([number]))
            descriptor = struct.unpack_from("<I", data, row["descriptor_offset"])[0]
            self.assertEqual(descriptor >> 28, 2)
            self.assertEqual(row["value_sha256"], hashlib.sha256(bytes([number])).hexdigest())
        empty = rows["/armor[1]/screen[1]"]
        self.assertEqual(empty["value_start"], empty["value_end"])
        self.assertIs(empty["value"], False)

    def test_corrupt_truncated_and_oversize_rejected(self):
        for data in (b"", sample()[:-1], sample() + b"x", b"WRNG" + sample()[4:]):
            with self.subTest(length=len(data)), self.assertRaises(packed_xml.FormatError):
                audit.field_offsets(data)
        with patch.object(audit, "MAX_BYTES", 10), self.assertRaises(packed_xml.FormatError):
            audit.field_offsets(sample())

    def test_ambiguous_logical_paths_cannot_misattribute_value_bytes(self):
        # Nested armor/screen and a literal tag named armor[1]/screen alias
        # in walk's textual paths, but carry different bytes. Reject both.
        names = b"armor\0screen\0armor[1]/screen\0\0"
        nested = struct.pack("<HIHI", 1, 0x10000000, 1, 0x20000001) + b"\x01"
        root = struct.pack("<HI", 2, 0x10000000)
        root += struct.pack("<HI", 0, len(nested))
        root += struct.pack("<HI", 2, 0x20000000 | (len(nested) + 1))
        data = packed_xml.MAGIC + b"\0" + names + root + nested + b"\x02"
        with self.assertRaisesRegex(audit.AuditError, "ambiguous"):
            audit.field_offsets(data)

    def test_source_paths_cannot_escape_or_read_other_formats(self):
        with tempfile.TemporaryDirectory(prefix="shell-mech-test-") as temp:
            root = Path(temp)
            for resource in ("../res/a.xml", "res/../../a.xml", "C:/res/a.xml",
                             "/res/a.xml", "res\\a.xml", "res/a.pyc", "a.xml"):
                with self.subTest(resource=resource), self.assertRaises(audit.AuditError):
                    audit.source_path(root, resource)

    def test_logical_path_expansion_is_bounded_before_collection(self):
        with patch.object(audit, "MAX_FIELD_PATH", 4), self.assertRaisesRegex(audit.AuditError, "length limit"):
            audit.field_offsets(sample())
        with patch.object(audit, "MAX_FIELD_PATH_TOTAL", 4), self.assertRaisesRegex(audit.AuditError, "aggregate"):
            audit.field_offsets(sample())

    def test_static_audit_preserves_source_and_reports_literal_selection(self):
        with tempfile.TemporaryDirectory(prefix="shell-mech-test-") as temp:
            root = Path(temp)
            (root / "res").mkdir()
            source = root / "res/a.xml"
            source.write_bytes(sample())
            result = audit.audit(root, ["res/a.xml"], ["/count["])
            self.assertEqual(source.read_bytes(), sample())
            self.assertEqual([row["value"] for row in result["sources"][0]["fields"]], [6, 4])
            self.assertEqual(result["sources"][0]["sha256"], hashlib.sha256(sample()).hexdigest())
            for resources, selects in ((["res/a.xml"] * 2, []), ([], []), (["res/a.xml"], [""])):
                with self.assertRaises(audit.AuditError):
                    audit.audit(root, resources, selects)
            with patch.object(audit, "MAX_TOTAL_BYTES", 1), self.assertRaises(audit.AuditError):
                audit.audit(root, ["res/a.xml"], [])

    def test_output_boundary_and_no_overwrite(self):
        with tempfile.TemporaryDirectory(prefix="shell-mech-test-") as temp:
            root = Path(temp)
            for name in ("receipt.json", "local/evidence/other/a.json",
                         "local/evidence/shell-mech-a.txt", "local/evidence/shell-mech-a/a.txt"):
                with self.subTest(name=name), self.assertRaises(audit.AuditError):
                    audit.write_receipt({}, root / name, root)
            output = root / "local/evidence/shell-mech-test/a.json"
            audit.write_receipt({"value": 1}, output, root)
            saved = output.read_bytes()
            with self.assertRaises(audit.AuditError):
                audit.write_receipt({"value": 2}, output, root)
            self.assertEqual(saved, output.read_bytes())

    def test_links_and_output_budget_rejected(self):
        with tempfile.TemporaryDirectory(prefix="shell-mech-test-") as temp:
            root = Path(temp)
            with patch.object(Path, "is_junction", return_value=True), self.assertRaises(audit.AuditError):
                audit.no_links(root)
            with patch.object(Path, "is_symlink", return_value=True), self.assertRaises(audit.AuditError):
                audit.no_links(root)
            output = root / "local/evidence/shell-mech-test/a.json"
            with patch.object(audit, "MAX_OUTPUT_BYTES", 1), self.assertRaises(audit.AuditError):
                audit.write_receipt({"value": "large"}, output, root)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
