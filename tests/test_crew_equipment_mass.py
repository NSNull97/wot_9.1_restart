"""Real #717 mass sources; synthetic owned-crew inputs test the domain boundary.

Nothing here demonstrates a native equipment installation or battle runtime.
"""
from __future__ import annotations

import copy
from dataclasses import FrozenInstanceError, replace
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from server.domain import crew_equipment as domain
from tools import crew_equipment_mass as mass
from tools.destructible_catalog import CatalogError, json_value
from tools.packed_xml import decode, walk
from tests.test_crew_equipment import candidate, encode, trusted, VENT1, VENT3, AIM, OPTICS


CONFIG = Path(os.environ.get("WOT091_CONFIG", mass.ROOT / "config/project.local.json"))
SCRATCH = mass.ROOT / "local/evidence/20261013-p04c-configuration-reservation-01/mass-source/test-scratch"


class MassSourceBoundaryTests(unittest.TestCase):
    def test_pinned_reader_rejects_mutation_truncation_oversize_empty(self):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=SCRATCH) as temp:
            path = Path(temp) / "synthetic-source.bin"
            pin = (3, hashlib.sha256(b"abc").hexdigest())
            for raw in (b"abd", b"ab", b"abcd", b""):
                path.write_bytes(raw)
                with self.subTest(raw=raw), self.assertRaises((mass.MassSourceError, CatalogError)):
                    mass._pinned_read(path, pin)

    def test_duplicate_config_key_wrong_build_bad_shape_fail_closed(self):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=SCRATCH) as temp:
            path = Path(temp) / "synthetic-config.json"
            for raw in (b'{"target":{},"target":{}}', b'{"target":{"exact_build":"modern"}}',
                        b'[]', b'null', b'{"target":true}', b'[' * 50 + b'0' + b']' * 50):
                path.write_bytes(raw)
                with self.subTest(raw=raw), self.assertRaises(mass.MassSourceError):
                    mass.load_verified_assemblies(path)

    def test_unknown_mount_ids_cannot_select_an_assembly(self):
        for mount_id in (None, True, 1, "vehicle:ms1", "MS-1", "ms1-upgraded", "../ms1-stock"):
            with self.subTest(mount_id=mount_id), self.assertRaises(mass.MassSourceError):
                mass.select_assembly((), mount_id)

    def test_mutable_snapshot_buffers_rejected(self):
        with self.assertRaises(mass.MassSourceError):
            mass.VerifiedAssembly(bytearray(b"{}"), b"{}")
        with self.assertRaises(mass.MassSourceError):
            mass.VerifiedAssembly(b"{}", bytearray(b"{}"))

    def test_output_must_be_fresh_within_worktree_evidence(self):
        with self.assertRaises(SystemExit):
            mass.main(["--config", str(CONFIG), "--out", str(mass.ROOT / "forbidden-mass-audit")])
        self.assertFalse((mass.ROOT / "forbidden-mass-audit").exists())
        SCRATCH.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=SCRATCH) as temp:
            path = Path(temp) / "receipt.json"
            path.write_bytes(b"preserved")
            with self.assertRaises(SystemExit):
                mass.main(["--config", str(CONFIG), "--out", temp])
            self.assertEqual(path.read_bytes(), b"preserved")


class Actual717MountedMassTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not CONFIG.is_file():
            raise unittest.SkipTest("NOT_RUN: set WOT091_CONFIG to the authorized #717 configuration")
        cls.assemblies = mass.load_verified_assemblies(CONFIG)
        cls.original, cls.local = mass._configured_paths(CONFIG)
        cls.sources = {name: mass._pinned_read(cls.original / name, pin)
                       for name, pin in mass.SOURCE_PINS.items()}
        cls.xml = {name[len(mass.XML_PREFIX):]: dict(walk(decode(raw)))
                   for name, raw in cls.sources.items() if name.endswith(".xml")}
        cls.native = {}
        for key, (relative, size, sha) in mass.NATIVE_PINS.items():
            cls.native[key] = json_value(mass._pinned_read(cls.local / relative, (size, sha)))["vehicle"]

    def _build(self, mount_id, devices):
        assembly = mass.select_assembly(self.assemblies, mount_id)
        value = candidate(assembly.vehicle_definition_id, devices)
        value["component_configuration_sha256"] = assembly.sha256
        raw = encode(value)
        binding = replace(trusted(raw, mass=assembly.mass_budget), component_configuration_sha256=assembly.sha256)
        return domain.build_snapshot(raw, binding=binding)

    def test_actual_ms1_complete_assembly_has_only_199kg_reserve(self):
        value = mass.select_assembly(self.assemblies, "ms1-stock").as_dict()
        self.assertEqual({r["role"]: r["mass_grams"] for r in value["components"]}, {
            "hull": 2750000, "chassis": 1200000, "engine": 266000, "fuelTank": 200000,
            "radio": 1000, "turret": 170000, "gun": 104000})
        self.assertEqual(value["base_mass_grams"], 4691000)
        self.assertEqual(value["max_load_grams"], 4890000)
        self.assertEqual(value["max_load_grams"] - value["base_mass_grams"], 199000)

    def test_actual_is7_full_stock_assembly_masses_and_ids(self):
        value = mass.select_assembly(self.assemblies, "is7-stock").as_dict()
        self.assertEqual(value["base_mass_grams"], 68190000)
        self.assertEqual(value["max_load_grams"], 70950000)
        self.assertEqual({r["role"]: r["native_compact_id"] for r in value["components"] if r["role"] != "hull"},
                         {"chassis": 14850, "engine": 9221, "fuelTank": 52486,
                          "radio": 2823, "turret": 12035, "gun": 14852})

    def test_ms1_ventilation_and_aim_drives_together_rejected_by_real_one_kg_excess(self):
        with self.assertRaisesRegex(domain.ConfigurationError, "load|mass|overweight"):
            self._build("ms1-stock", [VENT1, AIM, OPTICS])

    def test_ms1_each_mass_device_plus_optics_accepted(self):
        for device in (VENT1, AIM):
            with self.subTest(device=device):
                value = self._build("ms1-stock", [device, OPTICS, None]).as_dict()
                self.assertEqual(value["mass_check"]["total_mass_grams"], 4791000)
                self.assertFalse(value["runtime_ready"])

    def test_is7_three_allowlisted_devices_fit_real_source_budget(self):
        value = self._build("is7-stock", [VENT3, AIM, OPTICS]).as_dict()
        self.assertEqual(value["mass_check"]["total_mass_grams"], 68490000)
        self.assertEqual(value["mass_check"]["max_load_grams"], 70950000)

    def test_assembly_and_evidence_hashes_bind_budget_and_are_deterministic(self):
        second = mass.load_verified_assemblies(CONFIG)
        self.assertEqual(self.assemblies, second)
        self.assertNotEqual(self.assemblies[0].sha256, self.assemblies[1].sha256)
        for assembly in self.assemblies:
            self.assertEqual(assembly.sha256, hashlib.sha256(assembly.canonical_bytes).hexdigest())
            self.assertEqual(assembly.evidence_sha256, hashlib.sha256(assembly.evidence_bytes).hexdigest())
            self.assertEqual(assembly.mass_budget.component_configuration_sha256, assembly.sha256)
            self.assertEqual(assembly.mass_budget.evidence_sha256, assembly.evidence_sha256)
            self.assertEqual(assembly.evidence_dict()["component_configuration_sha256"], assembly.sha256)
            self.assertEqual(assembly.evidence_dict()["native_mass_readback"], "NOT_RUN")
            self.assertEqual(len(assembly.as_dict()["sources"]), 11)

    def test_snapshot_is_immutable_and_decoded_copies_detached(self):
        assembly = self.assemblies[0]
        with self.assertRaises(FrozenInstanceError):
            assembly.canonical_bytes = b"changed"
        decoded = assembly.as_dict()
        decoded["components"][0]["mass_grams"] = 0
        self.assertEqual(assembly.as_dict()["components"][0]["mass_grams"], 2750000)
        with self.assertRaises(FrozenInstanceError):
            assembly.mass_budget.base_mass_grams = 0

    def test_missing_or_duplicate_assembly_rejected(self):
        with self.assertRaises(mass.MassSourceError):
            mass.select_assembly((), "ms1-stock")
        with self.assertRaises(mass.MassSourceError):
            mass.select_assembly((self.assemblies[0], self.assemblies[0]), "ms1-stock")

    def test_each_component_native_id_mismatch_is_rejected(self):
        for spec in mass.ASSEMBLIES:
            for role in self.native[spec.mount_id]["components"]:
                native = copy.deepcopy(self.native[spec.mount_id])
                native["components"][role]["compact_descr"] += 256
                with self.subTest(mount=spec.mount_id, role=role), self.assertRaises(mass.MassSourceError):
                    mass._assembly_document(self.xml, native, spec)

    def test_same_vehicle_other_gun_descriptor_is_not_stock_assembly(self):
        native = copy.deepcopy(self.native["ms1-stock"])
        native["compact_descr_hex"] = "010d1a000e00c90000001700100000"
        with self.assertRaisesRegex(mass.MassSourceError, "mounted descriptor"):
            mass._assembly_document(self.xml, native, mass.ASSEMBLIES[0])

    def test_each_source_mass_id_and_maxload_mutation_rejected(self):
        fields = [("ms-1.xml", "/hull[1]/weight[1]"),
                  ("ms-1.xml", "/chassis[1]/T-18[1]/maxLoad[1]"),
                  ("ms-1.xml", "/chassis[1]/T-18[1]/weight[1]"),
                  ("ms-1.xml", "/turrets0[1]/T-18_Standart[1]/weight[1]"),
                  ("components/guns.xml", "/shared[1]/_37mm_Gochkins[1]/weight[1]"),
                  ("components/engines.xml", "/shared[1]/MS-1[1]/weight[1]"),
                  ("components/fuelTanks.xml", "/shared[1]/Small[1]/weight[1]"),
                  ("components/radios.xml", "/shared[1]/Alarm_flags[1]/weight[1]"),
                  ("components/chassis.xml", "/ids[1]/T-18[1]")]
        for name, key in fields:
            xml = copy.deepcopy(self.xml)
            xml[name][key] += 1
            with self.subTest(field=key), self.assertRaises(mass.MassSourceError):
                mass._assembly_document(xml, self.native["ms1-stock"], mass.ASSEMBLIES[0])

    def test_mounted_shared_mass_override_and_noninteger_mass_rejected(self):
        for name, key, value in [("ms-1.xml", "/engines[1]/MS-1[1]/weight[1]", 266),
                                 ("components/engines.xml", "/shared[1]/MS-1[1]/weight[1]", 266.0)]:
            xml = copy.deepcopy(self.xml)
            xml[name][key] = value
            with self.subTest(field=key), self.assertRaises(mass.MassSourceError):
                mass._assembly_document(xml, self.native["ms1-stock"], mass.ASSEMBLIES[0])

    def test_source_pin_drift_is_rejected_by_real_loader(self):
        pins = dict(mass.SOURCE_PINS)
        key = mass.XML_PREFIX + "components/fuelTanks.xml"
        pins[key] = (pins[key][0], "0" * 64)
        with patch.object(mass, "SOURCE_PINS", pins), self.assertRaisesRegex(mass.MassSourceError, "SHA256 mismatch"):
            mass.load_verified_assemblies(CONFIG)

    def test_native_export_pin_drift_is_rejected_by_real_loader(self):
        pins = dict(mass.NATIVE_PINS)
        name, size, _ = pins["is7-stock"]
        pins["is7-stock"] = (name, size, "0" * 64)
        with patch.object(mass, "NATIVE_PINS", pins), self.assertRaisesRegex(mass.MassSourceError, "SHA256 mismatch"):
            mass.load_verified_assemblies(CONFIG)


if __name__ == "__main__":
    unittest.main()
