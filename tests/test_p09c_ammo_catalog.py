"""Catalogue rejection tests; synthetic fields do not prove native compatibility."""
from copy import deepcopy
from dataclasses import FrozenInstanceError
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from tools import p09c_ammo_catalog as catalog


def source_field_fixture():
    """Only the exercised field boundary, not copied client XML or bytecode."""
    xml = {"list.xml": {"/MS-1[1]/id[1]": 13, "/IS-7[1]/id[1]": 28},
           "components/turrets.xml": {"/ids[1]/T-18_Standart[1]": 23,
                                      "/ids[1]/IS-7[1]": 47},
           "components/guns.xml": {"/ids[1]/_37mm_Gochkins[1]": 23,
                                    "/ids[1]/_130mm_S-70[1]": 58},
           "components/shells.xml": {}}
    # Intentionally contrary shared capacities: mounted overrides must win.
    for vehicle, turret, gun, capacity, shared_capacity, shells in (
        ("ms-1", "T-18_Standart", "_37mm_Gochkins", 96, 92,
         (("_37mm_UBRT1", 10, "ARMOR_PIERCING"),
          ("_37mm_BPT1", 11, "HOLLOW_CHARGE"),
          ("_37mm_UOT1", 12, "HIGH_EXPLOSIVE"))),
        ("is-7", "IS-7", "_130mm_S-70", 30, 28,
         (("_130mm_UBR-482", 57, "ARMOR_PIERCING"),
          ("_130mm_UBR-482P", 58, "ARMOR_PIERCING_CR"),
          ("_130mm_UOF-482", 59, "HIGH_EXPLOSIVE"))),
    ):
        base = f"/turrets0[1]/{turret}[1]/guns[1]/{gun}[1]"
        xml[vehicle + ".xml"] = {base: "shared", base + "/maxAmmo[1]": capacity}
        guns = xml["components/guns.xml"]
        guns[f"/shared[1]/{gun}[1]/maxAmmo[1]"] = shared_capacity
        for shell_name, shell_id, kind in shells:
            guns[f"/shared[1]/{gun}[1]/shots[1]/{shell_name}[1]"] = ""
            xml["components/shells.xml"][f"/{shell_name}[1]/id[1]"] = shell_id
            xml["components/shells.xml"][f"/{shell_name}[1]/kind[1]"] = kind
    return xml


class CatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_parent = catalog.ROOT / "local/evidence/p09c-catalog-unit-temp"
        cls.temp_parent.mkdir(parents=True, exist_ok=True)

    def test_catalog_immutable_and_document_detached(self):
        with self.assertRaises(TypeError):
            catalog.MOUNTS["new"] = catalog.MOUNTS["ms1-stock"]
        with self.assertRaises(TypeError):
            catalog.SHELLS["new"] = catalog.SHELLS["shell:ms1-stock-ap"]
        with self.assertRaises(FrozenInstanceError):
            catalog.MOUNTS["is7-stock"].capacity = 999
        with self.assertRaises(FrozenInstanceError):
            catalog.SHELLS["shell:is7-stock-ap"].item_id = 999
        document = catalog.catalog_document()
        document["mounts"]["is7-stock"]["capacity"] = 999
        self.assertEqual(30, catalog.MOUNTS["is7-stock"].capacity)

    def test_catalog_fingerprint_includes_source_and_domain_contract(self):
        document = catalog.catalog_document()
        raw = json.dumps(document, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=True, allow_nan=False).encode("ascii")
        self.assertEqual(catalog.CATALOG_SHA256, hashlib.sha256(raw).hexdigest())
        for mutation in ("sources", "mounts"):
            changed = deepcopy(document)
            changed[mutation].pop(next(iter(changed[mutation])))
            self.assertNotEqual(catalog.CATALOG_SHA256,
                                hashlib.sha256(catalog._canonical(changed)).hexdigest())
        self.assertEqual("UNSUPPORTED", document["prices"])
        self.assertEqual("NOT_RUN", document["native_is7_ammo"])

    def test_shared_capacity_cannot_replace_vehicle_override(self):
        fields = source_field_fixture()
        verified = catalog._validate_fields(fields)
        self.assertEqual([96, 30], [row["capacity"] for row in verified])
        path = "/turrets0[1]/IS-7[1]/guns[1]/_130mm_S-70[1]/maxAmmo[1]"
        fields["is-7.xml"][path] = 28
        with self.assertRaisesRegex(catalog.AmmoCatalogError, "field differs"):
            catalog._validate_fields(fields)
        del fields["is-7.xml"][path]
        with self.assertRaisesRegex(catalog.AmmoCatalogError, "field differs"):
            catalog._validate_fields(fields)

    def test_capacity_rejects_numeric_coercion(self):
        path = "/turrets0[1]/T-18_Standart[1]/guns[1]/_37mm_Gochkins[1]/maxAmmo[1]"
        for value in ("96", 96.0, True, None):
            with self.subTest(value=value):
                fields = source_field_fixture()
                fields["ms-1.xml"][path] = value
                with self.assertRaisesRegex(catalog.AmmoCatalogError, "field differs"):
                    catalog._validate_fields(fields)

    def test_shot_membership_order_and_duplicate_rejected(self):
        base = "/shared[1]/_130mm_S-70[1]/shots[1]/"
        for alteration in ("missing", "extra", "order", "duplicate"):
            with self.subTest(alteration=alteration):
                fields = source_field_fixture()
                guns = fields["components/guns.xml"]
                if alteration == "missing":
                    del guns[base + "_130mm_UBR-482P[1]"]
                elif alteration == "extra":
                    guns[base + "_37mm_UBRT1[1]"] = ""
                elif alteration == "duplicate":
                    guns[base + "_130mm_UBR-482[2]"] = ""
                else:
                    value = guns.pop(base + "_130mm_UBR-482[1]")
                    guns[base + "_130mm_UBR-482[1]"] = value
                with self.assertRaisesRegex(catalog.AmmoCatalogError, "ordered original shots"):
                    catalog._validate_fields(fields)

    def test_vehicle_shots_override_is_explicitly_unsupported(self):
        fields = source_field_fixture()
        fields["is-7.xml"]["/turrets0[1]/IS-7[1]/guns[1]/_130mm_S-70[1]/shots[1]"] = ""
        with self.assertRaisesRegex(catalog.AmmoCatalogError, "overrides shared"):
            catalog._validate_fields(fields)

    def test_shell_kind_or_id_mismatch_rejected(self):
        for key, value in (("id", 60), ("kind", "HOLLOW_CHARGE")):
            with self.subTest(key=key):
                fields = source_field_fixture()
                fields["components/shells.xml"][f"/_130mm_UBR-482P[1]/{key}[1]"] = value
                with self.assertRaisesRegex(catalog.AmmoCatalogError, "field differs"):
                    catalog._validate_fields(fields)

    def test_mount_component_mismatch_rejected(self):
        for file, path, value in (
            ("list.xml", "/IS-7[1]/id[1]", 29),
            ("components/turrets.xml", "/ids[1]/IS-7[1]", 48),
            ("components/guns.xml", "/ids[1]/_130mm_S-70[1]", 59),
            ("is-7.xml", "/turrets0[1]/IS-7[1]/guns[1]/_130mm_S-70[1]", ""),
        ):
            with self.subTest(file=file):
                fields = source_field_fixture()
                fields[file][path] = value
                with self.assertRaisesRegex(catalog.AmmoCatalogError, "field differs"):
                    catalog._validate_fields(fields)

    def test_source_activation_rejects_relative_missing_and_wrong_hash(self):
        with self.assertRaisesRegex(catalog.AmmoCatalogError, "absolute"):
            catalog.audit_sources(Path("relative"))
        with tempfile.TemporaryDirectory(dir=self.temp_parent) as directory:
            root = Path(directory)
            with self.assertRaises(catalog.AmmoCatalogError):
                catalog.audit_sources(root)
            relative, pin = next(iter(catalog.SOURCE_PINS.items()))
            target = root / relative
            target.parent.mkdir(parents=True)
            target.write_bytes(b"x" * pin.size)
            with self.assertRaisesRegex(catalog.AmmoCatalogError, "SHA256 mismatch"):
                catalog.audit_sources(root)
            self.assertEqual(b"x" * pin.size, target.read_bytes())

    def test_source_activation_rejects_oversized_and_traversal(self):
        with tempfile.TemporaryDirectory(dir=self.temp_parent) as directory:
            root = Path(directory)
            relative, pin = next(iter(catalog.SOURCE_PINS.items()))
            target = root / relative
            target.parent.mkdir(parents=True)
            target.write_bytes(b"x" * (pin.size + 1))
            with self.assertRaisesRegex(catalog.AmmoCatalogError, "bound"):
                catalog.audit_sources(root)
            with self.assertRaisesRegex(catalog.AmmoCatalogError, "traversal"):
                catalog.audit_sources(root / ".." / root.name)

    def test_cli_rejects_output_outside_own_evidence_without_writes(self):
        with tempfile.TemporaryDirectory(dir=self.temp_parent) as directory:
            root = Path(directory)
            # A path in the checkout is still forbidden unless under local/evidence.
            out = catalog.ROOT / "uncreated-p09c-output"
            with self.assertRaises(SystemExit) as raised:
                catalog.main(["--original-root", str(root), "--out", str(out)])
            self.assertEqual(1, raised.exception.code)
            self.assertFalse(out.exists())


if __name__ == "__main__":
    unittest.main()
